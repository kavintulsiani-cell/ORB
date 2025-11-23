import yfinance as yf
import pandas as pd
from SmartApi import SmartConnect

symbol = "SBIN.NS"
interval = "5m"
period = "60d" # ❗ IMPORTANT FIX

print("Downloading SBIN 5m data...")

df = yf.download(
    tickers=symbol,
    interval=interval,
    period=period,
    progress=False
)

# Drop MultiIndex second level cleanly
df.columns = [col[0].lower() if isinstance(col, tuple) else col.lower() for col in df.columns]

df = df.reset_index()
df = df.rename(columns={"datetime": "timestamp", "Datetime": "timestamp"})

df = df[["timestamp", "open", "high", "low", "close", "volume"]]

df["timestamp"] = pd.to_datetime(df["timestamp"])

# Filter trading hours
df = df[
    (df["timestamp"].dt.time >= pd.to_datetime("09:15").time()) &
    (df["timestamp"].dt.time <= pd.to_datetime("15:30").time())
]

df.to_csv("SBIN_5min.csv", index=False)

print("Saved SBIN_5min.csv successfully!")
print(df.head())