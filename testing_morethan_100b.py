# -*- coding: utf-8 -*-
"""
Created on Mon Mar  9 19:59:02 2026

@author: sakpb
"""

"""
=============================================================
  INDIA INTRADAY SHORT-SELL BACKTEST — 5-MIN CANDLES v3
=============================================================
  STRATEGY RULES:
  ───────────────
  Total Capital  : ₹7,00,000
  Data           : 5-minute intraday candles, last 60 days
  Universe       : NSE stocks (Nifty 500 representative)
  Filters        : Price > ₹100, Market Cap > ₹200 Billion
  Leverage       : 4x on each leg

  ENTRY LADDER (Martingale Short):
  ┌─────┬──────────────┬────────────┬──────────────────────────┐
  │ Leg │ Trigger      │ Capital    │ Notes                    │
  ├─────┼──────────────┼────────────┼──────────────────────────┤
  │  1  │ +7% from     │ ₹1,00,000  │ Opens position           │
  │     │ day open     │            │                          │
  │  2  │ +9% from     │ ₹2,00,000  │ Add to short             │
  │     │ day open     │            │                          │
  │  3  │ +11% from    │ ₹4,00,000  │ Final add; activates     │
  │     │ day open     │            │ ₹-4,000 stop-loss        │
  └─────┴──────────────┴────────────┴──────────────────────────┘

  EXIT RULES (priority order each candle):
  ┌───┬───────────────────────────────────────────────────────┐
  │ 1 │ FORCED CLOSE at 3:15PM candle open — no waiting       │
  ├───┼───────────────────────────────────────────────────────┤
  │ 2 │ LEG-3 STOP-LOSS: Combined P&L ≤ -₹4,000              │
  │   │ (only active when Leg 3 is entered)                   │
  ├───┼───────────────────────────────────────────────────────┤
  │ 3 │ PRICE STOP: +13% from day open → close all legs       │
  ├───┼───────────────────────────────────────────────────────┤
  │ 4 │ AFTER 2:30PM: If position is profitable (P&L > 0),    │
  │   │ close when combined P&L ≥ ₹500                        │
  ├───┼───────────────────────────────────────────────────────┤
  │ 5 │ BEFORE 2:30PM: Close when combined P&L ≥ ₹4,000       │
  └───┴───────────────────────────────────────────────────────┘
=============================================================
  Requirements:
    pip install yfinance pandas numpy tabulate
=============================================================
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
from tabulate import tabulate
import warnings
import time

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────
TOTAL_CAPITAL      = 700_000      # ₹7 Lakhs

LEVERAGE           = 4            # 4x on every leg
LEG_TRIGGERS       = [7, 9, 11]   # % from day open
LEG_CAPITALS       = [100_000, 200_000, 400_000]

PROFIT_TARGET      = 4_000        # ₹4,000 primary target (before 2:30PM)
REDUCED_TARGET     = 500          # ₹500 reduced target (after 2:30PM if profitable)
LEG3_STOPLOSS_RS   = -4_000       # -₹4,000 stop-loss when Leg 3 is active
PRICE_STOP_PCT     = 13           # Hard price stop at +13% from day open

TIME_REDUCED       = dtime(14, 30)  # 2:30 PM IST
TIME_FORCE_CLOSE   = dtime(15, 15)  # 3:15 PM IST

PRICE_FILTER       = 100
MCAP_FILTER        = 200e9

END_DATE   = datetime.today()
START_DATE = END_DATE - timedelta(days=60)

# ─────────────────────────────────────────────
#  STOCK UNIVERSE — NSE (Nifty 500 representative)
# ─────────────────────────────────────────────
STOCK_UNIVERSE = [
    # Nifty 50
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "LT.NS","AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS",
    "TITAN.NS","WIPRO.NS","ULTRACEMCO.NS","NESTLEIND.NS","POWERGRID.NS",
    "NTPC.NS","TATAMOTORS.NS","HCLTECH.NS","BAJFINANCE.NS","TECHM.NS",
    "ONGC.NS","COALINDIA.NS","JSWSTEEL.NS","TATASTEEL.NS","ADANIENT.NS",
    "ADANIPORTS.NS","BAJAJFINSV.NS","DRREDDY.NS","CIPLA.NS","EICHERMOT.NS",
    "HEROMOTOCO.NS","DIVISLAB.NS","APOLLOHOSP.NS","BRITANNIA.NS","GRASIM.NS",
    "BPCL.NS","HINDALCO.NS","M&M.NS","TATACONSUM.NS","SBILIFE.NS",
    "HDFCLIFE.NS","INDUSINDBK.NS","UPL.NS","SHREECEM.NS","PIDILITIND.NS",
    # Nifty Next 50
    "SIEMENS.NS","HAVELLS.NS","DABUR.NS","MARICO.NS","BERGEPAINT.NS",
    "MUTHOOTFIN.NS","LUPIN.NS","TORNTPHARM.NS","BIOCON.NS","AUROPHARMA.NS",
    "GODREJCP.NS","COLPAL.NS","PGHH.NS","SBICARD.NS","BANDHANBNK.NS",
    "FEDERALBNK.NS","IDFCFIRSTB.NS","PNB.NS","CANBK.NS","BANKBARODA.NS",
    "NMDC.NS","SAIL.NS","NATIONALUM.NS","VEDL.NS","HINDCOPPER.NS",
    "TATAPOWER.NS","ADANIGREEN.NS","ADANITRANS.NS","CESC.NS","TORNTPOWER.NS",
    "DLF.NS","GODREJPROP.NS","PRESTIGE.NS","OBEROIRLTY.NS","PHOENIXLTD.NS",
    "MCDOWELL-N.NS","RADICO.NS","UNITDSPR.NS","VBL.NS","BATAINDIA.NS",
    "PAGEIND.NS","TRENT.NS","ABFRL.NS","ZOMATO.NS","NYKAA.NS",
    "PAYTM.NS","POLICYBZR.NS","DELHIVERY.NS","VEDANT.NS","RAYMOND.NS",
    # Nifty Midcap 100
    "ABCAPITAL.NS","ALKEM.NS","APLLTD.NS","ATUL.NS","AUBANK.NS",
    "BALKRISIND.NS","BEL.NS","BHARATFORG.NS","BHEL.NS","CANFINHOME.NS",
    "CDSL.NS","CHOLAFIN.NS","CROMPTON.NS","CUMMINSIND.NS","DEEPAKNTR.NS",
    "EMAMILTD.NS","EXIDEIND.NS","GAIL.NS","GLENMARK.NS","GMRINFRA.NS",
    "HAL.NS","HINDPETRO.NS","INDHOTEL.NS","INDIGO.NS","IOC.NS",
    "IRCTC.NS","JUBLFOOD.NS","KAJARIACER.NS","KEC.NS","LALPATHLAB.NS",
    "LAURUSLABS.NS","LICHSGFIN.NS","LTTS.NS","MANAPPURAM.NS","MCX.NS",
    "METROPOLIS.NS","MPHASIS.NS","NAUKRI.NS","NBCC.NS","NHPC.NS",
    "OFSS.NS","PERSISTENT.NS","PETRONET.NS","POLYCAB.NS","PVRINOX.NS",
    "RBLBANK.NS","RELAXO.NS","SJVN.NS","SONACOMS.NS","SYNGENE.NS",
    "TATACHEM.NS","TATACOMM.NS","TVSMOTORS.NS","VOLTAS.NS","ZEEL.NS",
]
STOCK_UNIVERSE = list(dict.fromkeys(STOCK_UNIVERSE))


# ─────────────────────────────────────────────
#  STEP 1: FILTER STOCKS
# ─────────────────────────────────────────────
def filter_stocks(symbols):
    print(f"\n📊 Filtering {len(symbols)} stocks "
          f"(Price > ₹{PRICE_FILTER}, MCap > ₹{MCAP_FILTER/1e9:.0f}B)...\n")
    qualified, failed = [], []

    for sym in symbols:
        try:
            info  = yf.Ticker(sym).info
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0) or 0
            mcap  = info.get("marketCap", 0) or 0
            if price >= PRICE_FILTER and mcap >= MCAP_FILTER:
                qualified.append(sym)
                print(f"  ✅ {sym:<22} ₹{price:>8.2f}  MCap ₹{mcap/1e9:>8.1f}B")
            else:
                print(f"  ❌ {sym:<22} ₹{price:>8.2f}  MCap ₹{mcap/1e9:>8.1f}B  — filtered")
        except Exception:
            failed.append(sym)

    print(f"\n✅ {len(qualified)} passed | ❌ {len(symbols)-len(qualified)} filtered "
          f"| ⚠️  {len(failed)} errors\n")
    return qualified


# ─────────────────────────────────────────────
#  STEP 2: DOWNLOAD 5-MIN INTRADAY DATA
# ─────────────────────────────────────────────
def download_5min_data(symbols):
    print(f"📥 Downloading 5-min data for {len(symbols)} stocks (last 60 days)...\n")
    data = {}

    for i, sym in enumerate(symbols, 1):
        try:
            df = yf.download(sym, period="60d", interval="5m",
                             progress=False, auto_adjust=True)
            if len(df) > 50:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
                data[sym] = df
                print(f"  ✅ [{i:>3}/{len(symbols)}] {sym:<22} {len(df):>5} candles")
            else:
                print(f"  ⚠️  [{i:>3}/{len(symbols)}] {sym:<22} insufficient data")
        except Exception as e:
            print(f"  ❌ [{i:>3}/{len(symbols)}] {sym:<22} {str(e)[:55]}")
        if i % 10 == 0:
            time.sleep(1)

    print(f"\n📦 Data ready for {len(data)} stocks\n")
    return data


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def _combined_pnl(legs_active, entry_prices, test_price):
    """
    Short P&L = sum_i [ (entry_i - test_price) / entry_i * (capital_i * leverage) ]
    Positive = profit (price fell below entry)
    Negative = loss  (price rose above entry)
    """
    total = 0.0
    for i in range(3):
        if legs_active[i] and entry_prices[i] > 0:
            notional = LEG_CAPITALS[i] * LEVERAGE
            total   += ((entry_prices[i] - test_price) / entry_prices[i]) * notional
    return total


def _price_at_pnl(legs_active, entry_prices, target_pnl):
    """
    Solve exactly for exit_price where combined P&L = target_pnl.
    Derivation:
      sum_i [ (e_i - x) / e_i * N_i ] = T
      sum_i N_i  -  x * sum_i (N_i / e_i) = T
      x = (sum_i N_i - T) / sum_i (N_i / e_i)
    """
    sum_notional = sum(LEG_CAPITALS[i] * LEVERAGE for i in range(3) if legs_active[i])
    sum_w        = sum(
        (LEG_CAPITALS[i] * LEVERAGE) / entry_prices[i]
        for i in range(3) if legs_active[i] and entry_prices[i] > 0
    )
    if sum_w == 0:
        return 0.0
    return round((sum_notional - target_pnl) / sum_w, 2)


def _capital_used(legs_active):
    return sum(LEG_CAPITALS[i] for i in range(3) if legs_active[i])


def _make_result(day, sym, day_open, legs_active, entry_prices, exit_px, reason, pnl):
    return {
        "Date"        : str(day),
        "Stock"       : sym.replace(".NS", ""),
        "Day Open"    : round(day_open, 2),
        "Legs Hit"    : sum(legs_active),
        "Leg1 Entry"  : round(entry_prices[0], 2) if legs_active[0] else "-",
        "Leg2 Entry"  : round(entry_prices[1], 2) if legs_active[1] else "-",
        "Leg3 Entry"  : round(entry_prices[2], 2) if legs_active[2] else "-",
        "Exit Price"  : round(exit_px, 2),
        "Exit Reason" : reason,
        "Capital Used": _capital_used(legs_active),
        "P&L ₹"       : round(pnl, 2),
        "Outcome"     : "WIN" if pnl >= 0 else "LOSS",
    }


# ─────────────────────────────────────────────
#  STEP 3: BACKTEST ENGINE
# ─────────────────────────────────────────────
def run_backtest(data):
    print("🔍 Running Multi-Leg Intraday Backtest (5-min candles)...\n")
    print(f"  Leg1 ₹1L×4x → SHORT at +7%   |  Leg2 ₹2L×4x → SHORT at +9%   |  Leg3 ₹4L×4x → SHORT at +11%")
    print(f"  Main target  : ₹{PROFIT_TARGET:,} (before 2:30PM)")
    print(f"  Late target  : ₹{REDUCED_TARGET} after 2:30PM if position is profitable")
    print(f"  Leg3 SL      : Combined P&L ≤ -₹{abs(LEG3_STOPLOSS_RS):,}")
    print(f"  Price Stop   : +{PRICE_STOP_PCT}% from day open")
    print(f"  Forced Close : 3:15PM candle open price (no waiting)")
    print("─" * 85)

    all_trades, daily_pnl = [], {}

    for sym, df in data.items():
        df = df.copy().sort_index()
        df.index = pd.to_datetime(df.index)
        df["_date"] = df.index.date

        for day, day_df in df.groupby("_date"):
            day_df = day_df.sort_index()
            if len(day_df) < 10:
                continue

            day_open = float(day_df["Open"].iloc[0])
            if day_open <= 0:
                continue

            trig_px   = [day_open * (1 + p / 100) for p in LEG_TRIGGERS]  # +7, +9, +11%
            stop_px13 = day_open * (1 + PRICE_STOP_PCT / 100)              # +13%

            legs_active  = [False, False, False]
            entry_prices = [0.0, 0.0, 0.0]
            position_on  = False
            trade_result = None

            for ts, row in day_df.iterrows():
                ctime  = ts.time()
                c_open = float(row["Open"])
                c_high = float(row["High"])
                c_low  = float(row["Low"])

                # ── PRIORITY 1: FORCED CLOSE at 3:15PM ─────────────────────
                if ctime >= TIME_FORCE_CLOSE:
                    if position_on:
                        pnl = _combined_pnl(legs_active, entry_prices, c_open)
                        trade_result = _make_result(
                            day, sym, day_open, legs_active, entry_prices,
                            c_open, "FORCED CLOSE 3:15PM", pnl)
                    break  # done for the day

                if position_on:
                    # ── PRIORITY 2: LEG-3 STOP-LOSS (-₹4,000) ──────────────
                    if legs_active[2]:
                        worst_pnl = _combined_pnl(legs_active, entry_prices, c_high)
                        if worst_pnl <= LEG3_STOPLOSS_RS:
                            exit_px = _price_at_pnl(legs_active, entry_prices, LEG3_STOPLOSS_RS)
                            trade_result = _make_result(
                                day, sym, day_open, legs_active, entry_prices,
                                exit_px, f"LEG3 STOP-LOSS -₹{abs(LEG3_STOPLOSS_RS):,}",
                                LEG3_STOPLOSS_RS)
                            break

                    # ── PRIORITY 3: PRICE STOP +13% ────────────────────────
                    if c_high >= stop_px13:
                        pnl = _combined_pnl(legs_active, entry_prices, stop_px13)
                        trade_result = _make_result(
                            day, sym, day_open, legs_active, entry_prices,
                            stop_px13, f"PRICE STOP +{PRICE_STOP_PCT}%", pnl)
                        break

                    # ── PRIORITY 4: AFTER 2:30PM — reduced ₹500 target ─────
                    if ctime >= TIME_REDUCED:
                        current_pnl = _combined_pnl(legs_active, entry_prices, c_low)
                        if current_pnl > 0:  # position is profitable
                            best_pnl = _combined_pnl(legs_active, entry_prices, c_low)
                            if best_pnl >= REDUCED_TARGET:
                                exit_px = _price_at_pnl(legs_active, entry_prices, REDUCED_TARGET)
                                trade_result = _make_result(
                                    day, sym, day_open, legs_active, entry_prices,
                                    exit_px,
                                    f"REDUCED TARGET ₹{REDUCED_TARGET} (after 2:30PM)",
                                    REDUCED_TARGET)
                                break

                    else:
                        # ── PRIORITY 5: MAIN TARGET ₹4,000 (before 2:30PM) ─
                        best_pnl = _combined_pnl(legs_active, entry_prices, c_low)
                        if best_pnl >= PROFIT_TARGET:
                            exit_px = _price_at_pnl(legs_active, entry_prices, PROFIT_TARGET)
                            trade_result = _make_result(
                                day, sym, day_open, legs_active, entry_prices,
                                exit_px,
                                f"PROFIT TARGET ₹{PROFIT_TARGET:,}",
                                PROFIT_TARGET)
                            break

                # ── CHECK NEW LEG ENTRIES ────────────────────────────────────
                # Leg 1 @ +7%
                if not legs_active[0] and c_high >= trig_px[0]:
                    legs_active[0]  = True
                    entry_prices[0] = trig_px[0]
                    position_on     = True

                # Leg 2 @ +9% (only after Leg 1)
                if legs_active[0] and not legs_active[1] and c_high >= trig_px[1]:
                    legs_active[1]  = True
                    entry_prices[1] = trig_px[1]

                # Leg 3 @ +11% (only after Leg 2)
                if legs_active[1] and not legs_active[2] and c_high >= trig_px[2]:
                    legs_active[2]  = True
                    entry_prices[2] = trig_px[2]

            # Safety fallback if loop ends without a trade_result
            if position_on and trade_result is None:
                last_px = float(day_df["Close"].iloc[-1])
                pnl = _combined_pnl(legs_active, entry_prices, last_px)
                trade_result = _make_result(
                    day, sym, day_open, legs_active, entry_prices,
                    last_px, "EOD FALLBACK", pnl)

            if trade_result:
                all_trades.append(trade_result)
                key = str(day)
                daily_pnl[key] = daily_pnl.get(key, 0) + trade_result["P&L ₹"]

    return pd.DataFrame(all_trades), daily_pnl


# ─────────────────────────────────────────────
#  STEP 4: PERFORMANCE SUMMARY
# ─────────────────────────────────────────────
def print_summary(trades_df, daily_pnl):
    if trades_df.empty:
        print("\n⚠️  No trades triggered in backtest period.")
        return

    total_trades = len(trades_df)
    wins         = trades_df[trades_df["Outcome"] == "WIN"]
    losses       = trades_df[trades_df["Outcome"] == "LOSS"]
    win_rate     = len(wins) / total_trades * 100
    total_pnl    = trades_df["P&L ₹"].sum()
    avg_pnl      = trades_df["P&L ₹"].mean()
    exit_counts  = trades_df["Exit Reason"].value_counts().to_dict()

    max_dd = 0
    if daily_pnl:
        ds     = pd.Series(daily_pnl).sort_index()
        cum    = ds.cumsum()
        max_dd = (cum - cum.cummax()).min()

    print("\n" + "=" * 70)
    print("       📈 INTRADAY MULTI-LEG SHORT-SELL — PERFORMANCE SUMMARY  v3")
    print("=" * 70)

    rows = [
        ["Period",                   f"{START_DATE.date()} → {END_DATE.date()} (60 days)"],
        ["Data",                     "5-Min Intraday Candles (NSE)"],
        ["Stocks Tested",            f"{trades_df['Stock'].nunique()} stocks"],
        ["Total Trades",             total_trades],
        ["Winning Trades",           f"{len(wins):>4}  ({win_rate:.1f}%)"],
        ["Losing Trades",            f"{len(losses):>4}  ({100-win_rate:.1f}%)"],
        ["Total Net P&L",            f"₹{total_pnl:>12,.2f}"],
        ["Avg P&L / Trade",          f"₹{avg_pnl:>12,.2f}"],
        ["Max Drawdown (cumulative)",f"₹{max_dd:>12,.2f}"],
        ["ROI on ₹7L Capital",       f"{(total_pnl/TOTAL_CAPITAL)*100:.2f}%"],
        ["── EXIT BREAKDOWN ──",     ""],
        ["  ₹4,000 Profit Target",   exit_counts.get(f"PROFIT TARGET ₹{PROFIT_TARGET:,}", 0)],
        ["  ₹500 Reduced Target",    exit_counts.get(f"REDUCED TARGET ₹{REDUCED_TARGET} (after 2:30PM)", 0)],
        ["  Leg3 Stop-Loss -₹4,000", exit_counts.get(f"LEG3 STOP-LOSS -₹{abs(LEG3_STOPLOSS_RS):,}", 0)],
        ["  Price Stop +13%",        exit_counts.get(f"PRICE STOP +{PRICE_STOP_PCT}%", 0)],
        ["  Forced Close 3:15PM",    exit_counts.get("FORCED CLOSE 3:15PM", 0)],
        ["── STRATEGY CONFIG ──",    ""],
        ["  Leg 1  ₹1L × 4x",        "Short at +7%   | no independent SL"],
        ["  Leg 2  ₹2L × 4x",        "Short at +9%   | no independent SL"],
        ["  Leg 3  ₹4L × 4x",        "Short at +11%  | activates -₹4,000 combined SL"],
        ["  Main Target",             "₹4,000 combined (before 2:30PM)"],
        ["  Late Target",             "₹500 combined if profitable after 2:30PM"],
        ["  Price Hard Stop",         "+13% from day open"],
        ["  No EOD wait",             "All positions close at 3:15PM candle open"],
    ]
    print(tabulate(rows, tablefmt="rounded_outline"))

    # Leg trigger distribution
    print("\n📊 Leg Trigger Distribution:\n")
    leg_dist = trades_df["Legs Hit"].value_counts().sort_index()
    max_count = leg_dist.max()
    for legs, count in leg_dist.items():
        bar = "█" * int(count / max_count * 40)
        pct = count / total_trades * 100
        print(f"  {legs} Leg(s) : {bar:<40} {count:>4} trades  ({pct:.1f}%)")

    # Daily P&L sparkline
    if daily_pnl:
        print("\n📅 Daily Net P&L (last 30 trading days):\n")
        ds = pd.Series(daily_pnl).sort_index().tail(30)
        max_abs = max(abs(ds).max(), 1)
        for d, v in ds.items():
            bar = int(abs(v) / max_abs * 28)
            sym = "▲" if v >= 0 else "▼"
            blk = "█" * bar
            print(f"  {d}  {sym} {blk:<28}  ₹{v:>10,.0f}")

    # Top 20 stocks
    print("\n\n📋 TOP 20 STOCKS BY NET P&L:\n")
    sg = trades_df.groupby("Stock").agg(
        Trades   = ("P&L ₹","count"),
        Net_PnL  = ("P&L ₹","sum"),
        Wins     = ("Outcome", lambda x: (x=="WIN").sum()),
        Avg_PnL  = ("P&L ₹","mean"),
        Max_Legs = ("Legs Hit","max"),
    ).reset_index()
    sg["Win%"]    = (sg["Wins"] / sg["Trades"] * 100).round(1)
    sg["Net_PnL"] = sg["Net_PnL"].round(2)
    sg["Avg_PnL"] = sg["Avg_PnL"].round(2)
    print(tabulate(
        sg.sort_values("Net_PnL", ascending=False).head(20)
          [["Stock","Trades","Net_PnL","Win%","Avg_PnL","Max_Legs"]].values.tolist(),
        headers=["Stock","Trades","Net P&L ₹","Win%","Avg P&L ₹","Max Legs"],
        tablefmt="rounded_outline"
    ))

    # Full trade log
    print("\n\n📋 TRADE LOG (most recent 60 trades):\n")
    cols = ["Date","Stock","Day Open","Legs Hit","Leg1 Entry","Leg2 Entry",
            "Leg3 Entry","Exit Price","Exit Reason","Capital Used","P&L ₹","Outcome"]
    print(tabulate(
        trades_df[cols].tail(60).values.tolist(),
        headers=cols, tablefmt="rounded_outline"
    ))

    out_csv = "backtest_results_intraday.csv"
    trades_df.to_csv(out_csv, index=False)
    print(f"\n💾 Full trade log saved → {out_csv}")

    print("\n" + "=" * 70)
    verdict = "✅ PROFITABLE" if total_pnl > 0 else "❌ UNPROFITABLE"
    print(f"  Strategy Verdict   : {verdict}")
    print(f"  Net P&L (60 days)  : ₹{total_pnl:,.2f}")
    print(f"  ROI on ₹7L Capital : {(total_pnl/TOTAL_CAPITAL)*100:.2f}%")
    print("=" * 70)


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("   🇮🇳  INDIA INTRADAY MULTI-LEG SHORT-SELL BACKTEST  v3")
    print("   📊  5-Min Candles | 60 Days | Nifty 500 Universe")
    print("=" * 70)

    qualified = filter_stocks(STOCK_UNIVERSE)
    if not qualified:
        print("❌ No stocks passed filters. Exiting.")
        exit()

    market_data = download_5min_data(qualified)
    if not market_data:
        print("❌ No data downloaded. Check internet connection.")
        exit()

    trades_df, daily_pnl = run_backtest(market_data)
    print_summary(trades_df, daily_pnl)