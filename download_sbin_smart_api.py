from SmartApi import SmartConnect
import pyotp
import pandas as pd
from datetime import datetime

API_KEY = "JRyUUxSU"
CLIENT_ID = "K339542"
PIN = "0586"
TOTP_SECRET = "LRWKXRNC7RVJI7TV7QJV753FBM"

def login():
    smart = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    smart.generateSession(CLIENT_ID, PIN, totp)
    return smart

def download_sbin_5min(smart):
    SBIN_TOKEN = "3045" # SBIN EQ token

    params = {
        "exchange": "NSE",
        "symboltoken": SBIN_TOKEN,
        "interval": "FIVE_MINUTE",
        "fromdate": "2025-01-01 09:15",
        "todate": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    try:
        data = smart.getCandleData(params)
        candles = data["data"]

        df = pd.DataFrame(candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume"
        ])

        print(df.head())
        df.to_csv("SBIN_5min_SmartAPI.csv", index=False)
        print("Saved SBIN_5min_SmartAPI.csv successfully!")

    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    smart = login()
    download_sbin_5min(smart)
