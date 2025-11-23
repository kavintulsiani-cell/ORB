from SmartApi import SmartConnect
import pyotp
from datetime import datetime, timedelta
import pandas as pd

API_KEY = "JRyUUxSU"
CLIENT_ID = "K339542"
PIN = "0586"
TOTP_SECRET = "LRWKXRNC7RVJI7TV7QJV753FBM"

# NOTE: These are the usual SmartAPI tokens for indices.
# If you get "no data", we’ll pull the exact tokens from your ScripMaster JSON.
NIFTY_TOKEN = "99926000" # NIFTY 50 index
BANKNIFTY_TOKEN = "99926009" # BANKNIFTY index
EXCHANGE = "NSE"


def login():
    smart = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    smart.generateSession(CLIENT_ID, PIN, totp)
    print("LOGIN SUCCESS")
    return smart


def download_index(smart, symboltoken: str, name: str, days: int = 90):
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    params = {
        "exchange": EXCHANGE,
        "symboltoken": symboltoken,
        "interval": "FIVE_MINUTE",
        "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
        "todate": to_date.strftime("%Y-%m-%d %H:%M"),
    }

    print(f"\nDownloading {name} 5m data...")
    data = smart.getCandleData(params)

    candles = data.get("data")
    if not candles:
        print(f"ERROR: No data returned for {name}. Token may be different.")
        return

    df = pd.DataFrame(
        candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    csv_name = f"{name}_5min_SmartAPI.csv"
    df.to_csv(csv_name, index=False)
    print(f"Saved {csv_name} successfully!")
    print(df.head())


if __name__ == "__main__":
    smart = login()
    download_index(smart, NIFTY_TOKEN, "NIFTY")
    download_index(smart, BANKNIFTY_TOKEN, "BANKNIFTY")
