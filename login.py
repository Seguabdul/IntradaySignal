import neo_api_client
from neo_api_client import NeoAPI
client = NeoAPI(environment='prod', access_token=None, neo_fin_key=None, consumer_key='9d01eff0-5acc-4c56-9302-711fe4852b70')
loginflag=0
def login():
    
    code=input("enter auth code")
    
    client.totp_login(mobile_number="+919087222849", ucc="Y3AJH", totp=code)
    try:
        print(client.totp_validate(mpin="786786"))
        
    except Exception as e:
        print("Exception when calling TOTPLogin ->totp_validate: %s\n" % e)
    
    
    print(client)



login()
