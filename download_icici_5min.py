from SmartApi import SmartConnect
import pyotp
from datetime import datetime, timedelta
import pandas as pd

API_KEY = "JRyUUxSU"
CLIENT_ID = "K339542"
PIN = "0586"
TOTP_SECRET = "LRWKXRNC7RVJI7TV7QJV753FBM"

# ICICIBANK token (NSE)
ICICI_TOKEN = "1270"
EXCHANGE = "NSE"

def login():
    smart = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    data = smart.generateSession(CLIENT_ID, PIN, totp)
    print("LOGIN SUCCESS")
    return smart

def download_icici_5min():
    smart = login()

    to_date = datetime.now()
    from_date = to_date - timedelta(days=90)

    params = {
        "exchange": EXCHANGE,
        "symboltoken": ICICI_TOKEN,
        "interval": "FIVE_MINUTE",
        "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
        "todate": to_date.strftime("%Y-%m-%d %H:%M")
    }

    print("Downloading ICICIBANK data...")

    historic = smart.getCandleData(params)

    df = pd.DataFrame(historic["data"],
                      columns=["timestamp", "open", "high", "low", "close", "volume"])

    df.to_csv("ICICIBANK_5min_SmartAPI.csv", index=False)
    print("Saved ICICIBANK_5min_SmartAPI.csv successfully!")
    print(df.head())

if __name__ == "__main__":
    download_icici_5min()
