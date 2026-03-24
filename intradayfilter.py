"""
NSE Stock Screener using yfinance + Multithreading
==================================================
Screen 1 — LARGE CAP  : Price > 100 INR | Change > 5%  | Market Cap > 200 B INR
Screen 2 — MID CAP    : Price > 100 INR | Change > 10% | Market Cap 10 B – 200 B INR

FIX: Uses history(period="2d") for accurate prev-close → change %
     (fast_info.previous_close can return stale/wrong data)
"""

import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
import warnings
warnings.filterwarnings("ignore")

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RED    = "\033[91m"
RESET  = "\033[0m"
DIM    = "\033[2m"

# ── NSE universe (append ".NS" for yfinance) ──────────────────────────────────
NSE_TICKERS = [
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN","BAJFINANCE",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","TITAN",
    "SUNPHARMA","ULTRACEMCO","NESTLEIND","WIPRO","POWERGRID","NTPC","ONGC",
    "TECHM","HCLTECH","ADANIENT","ADANIPORTS","TMCV","TATASTEEL","JSWSTEEL",
    "HINDALCO","BAJAJFINSV","BPCL","COALINDIA","DRREDDY","EICHERMOT","GRASIM",
    "DIVISLAB","CIPLA","APOLLOHOSP","HEROMOTOCO","BRITANNIA","SBILIFE","HDFCLIFE",
    "INDUSINDBK","M&M","SHREECEM","TATACONSUM","UPL","LTIM","BAJAJ-AUTO",
    # Nifty Next 50 / popular mid-caps
    "ADANIGREEN","ADANITRANS","ATGL","NAUKRI","PIDILITIND","SIEMENS","HAVELLS",
    "BERGEPAINT","MUTHOOTFIN","CHOLAFIN","PFC","RECLTD","IRCTC","ZOMATO","NYKAA",
    "PAYTM","DMART","TRENT","TORNTPHARM","LUPIN","BIOCON","AUROPHARMA","ALKEM",
    "MANKIND","MAXHEALTH","FORTIS","LALPATHLAB","METROPOLIS","IPCALAB","ABBOTINDIA",
    "VOLTAS","BLUESTARCO","POLYCAB","DIXON","AMBER","KAYNES","SYRMA","PGEL",
    "TIINDIA","MOTHERSON","BALKRISIND","MRF","APOLLOTYRE","CEAT","EXIDEIND",
    "AMBUJACEM","ACC","RAMCOCEM","JKCEMENT","HEIDELBERG","DALBHARAT",
    "BANKBARODA","PNB","CANBK","UNIONBANK","IDFCFIRSTB","FEDERALBNK","RBLBANK",
    "PERSISTENT","MPHASIS","COFORGE","KPITTECH","ZENSARTECH","CYIENT","HEXAWARE",
    "TATAPOWER","CESC","TORNTPOWER","JSPL","NMDC","HINDCOPPER","NATIONALUM",
    "PIIND","RALLIS","ATUL","NAVINFLUOR","DEEPAKNTR","FINEORG","AAVAS",
    "GOCLCORP","IRFC","RVNL","RAILTEL","NBCC","BEL","HAL","COCHINSHIP","GRSE",
    "VEDL","SAIL","MOIL","GMRINFRA","ZEEL","PVR","INOXLEISURE","PCBL","GHCL",
    "TATAELXSI","ROUTE","FIVESTAR","CREDITACC","UGROCAP","SBFC","UTIAMC",
    "NIPPONLIFE","ABSLAMC","360ONE","ANGELONE","ICICIPRULI","STARHEALTH",
    "GAIL","OIL","MRPL","CHENNPETRO","CASTROLIND","IOC","HPCL",
    "GODREJPROP","DLF","PRESTIGE","BRIGADE","OBEROIRLTY","PHOENIXLTD",
    "COLPAL","DABUR","MARICO","EMAMILTD","GODREJCP","VBL","RADICO","UBL",
    "WHIRLPOOL","BLUESTAR","CROMPTON","BATAINDIA","VIPIND","PRINCEPIPE",
    "APTUS","CANFINHOME","HOMEFIRST","GRUH","REPCO","EDELWEISS",
    "MFSL","POONAWALLA","SUNDARMFIN","MANAPPURAM","GOLDFINCH","NOCIL","PRECAM"
]

# Remove duplicates
NSE_TICKERS = list(dict.fromkeys(NSE_TICKERS))


# ── Constants ─────────────────────────────────────────────────────────────────
B = 1_000_000_000   # 1 billion

SCREEN1 = dict(price_min=100, change_min=5,  mcap_min=200*B, mcap_max=float("inf"))
SCREEN2 = dict(price_min=100, change_min=10, mcap_min=10*B,  mcap_max=200*B)

MAX_WORKERS = 40     # parallel threads
TIMEOUT     = 8      # seconds per ticker


# ── Fetch one ticker ───────────────────────────────────────────────────────────
def fetch(sym: str) -> dict | None:
    """
    WHY history(period='2d') instead of fast_info:
      • fast_info.previous_close is often stale (cached from prior session or wrong)
      • history() gives OHLCV for last 2 actual trading days — same source TradingView uses
      • row[-1].close  = today's last traded price
      • row[-2].close  = yesterday's official closing price  ← true prev-close
      • change %  = (today_close - prev_close) / prev_close * 100
    """
    ticker_sym = sym + ".NS"
    try:
        t = yf.Ticker(ticker_sym)

        # --- accurate price & change via 2-day OHLCV history ---
        hist = t.history(period="2d", interval="1d", auto_adjust=True)
        if hist is None or len(hist) < 2:
            return None

        today_close = float(hist["Close"].iloc[-1])
        prev_close  = float(hist["Close"].iloc[-2])
        today_vol   = float(hist["Volume"].iloc[-1])

        if prev_close == 0:
            return None

        change_pct = (today_close - prev_close) / prev_close * 100

        # --- market cap: fast_info is fine for this (it doesn't change intraday) ---
        fi   = t.fast_info
        mcap = fi.market_cap        # may be None for illiquid stocks
        if mcap is None:
            # fallback: shares_outstanding * price
            info = t.info
            shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            mcap   = shares * today_close if shares else None
        if mcap is None:
            return None

        return {
            "symbol"    : sym,
            "price"     : today_close,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "mcap"      : mcap,
            "volume"    : today_vol,
        }
    except Exception:
        return None


# ── Apply screen filters ───────────────────────────────────────────────────────
def matches(row: dict, screen: dict) -> bool:
    return (
        row["price"]      >  screen["price_min"]
        and row["change_pct"] >= screen["change_min"]
        and screen["mcap_min"] <= row["mcap"] < screen["mcap_max"]
    )


# ── Pretty-print a results table ───────────────────────────────────────────────
def fmt_mcap(v: float) -> str:
    if v >= 1_000*B: return f"{v/1_000/B:6.1f} T"
    return             f"{v/B:6.2f} B"

def fmt_change(v: float) -> str:
    colour = GREEN if v >= 0 else RED
    return f"{colour}{v:+.2f}%{RESET}"

def print_table(title: str, colour: str, rows: list[dict]) -> None:
    W = 120
    print(f"\n{colour}{BOLD}{'─'*W}")
    print(f"  {title}")
    print(f"{'─'*W}{RESET}")

    hdr = (f"  {'Symbol':<14} {'Price (INR)':>12} {'Prev Close':>12} {'Change %':>10} "
           f"{'Market Cap':>12} {'Volume':>14}")
    print(f"{BOLD}{hdr}{RESET}")
    print(f"{DIM}{'  ' + '─'*116}{RESET}")

    for r in rows:
        chg   = fmt_change(r["change_pct"])
        mcap  = fmt_mcap(r["mcap"])
        vol   = f"{r['volume']:,.0f}"
        line  = (f"  {r['symbol']:<14} {r['price']:>12.2f} {r['prev_close']:>12.2f} {chg:>18} "
                 f"{mcap:>12} {vol:>14}")
        print(line)

    print(f"{colour}{BOLD}{'─'*W}{RESET}")
    print(f"  {colour}{BOLD}{len(rows)} stock(s) matched{RESET}\n")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{CYAN}{BOLD}  NSE Stock Screener  —  {datetime.now().strftime('%d %b %Y  %H:%M:%S')}{RESET}")
    print(f"{DIM}  Fetching {len(NSE_TICKERS)} tickers with {MAX_WORKERS} threads …{RESET}\n")

    results: list[dict] = []
    start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch, sym): sym for sym in NSE_TICKERS}
        done = 0
        for fut in as_completed(futures):
            done += 1
            data = fut.result()
            if data:
                results.append(data)
            # Live progress bar
            pct  = done / len(NSE_TICKERS)
            bar  = "█" * int(pct * 40) + "░" * (40 - int(pct * 40))
            print(f"\r  [{bar}] {done}/{len(NSE_TICKERS)}  fetched", end="", flush=True)

    print(f"\n\n  {BOLD}Done in {time.time()-start:.1f}s{RESET}  —  "
          f"{len(results)} tickers returned data.\n")

    # ── Screen 1 : LARGE CAP ──────────────────────────────────────────────────
    s1 = sorted(
        [r for r in results if matches(r, SCREEN1)],
        key=lambda x: x["mcap"], reverse=True
    )
    print_table(
        f"SCREEN 1 — LARGE CAP  |  Price > 100 INR  |  Change ≥ +5%  |  Market Cap > 200 B INR",
        CYAN, s1
    )

    # ── Screen 2 : MID CAP ───────────────────────────────────────────────────
    s2 = sorted(
        [r for r in results if matches(r, SCREEN2)],
        key=lambda x: x["mcap"], reverse=True
    )
    print_table(
        f"SCREEN 2 — MID CAP   |  Price > 100 INR  |  Change ≥ +10% |  Market Cap 10 B – 200 B INR",
        YELLOW, s2
    )


if __name__ == "__main__":
    main()