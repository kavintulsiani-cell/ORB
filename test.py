import yfinance as yf
import pandas as pd

df = yf.download("SBIN.NS", interval="5m", period="1mo")

print(df.columns)
df = df.reset_index()
print("\nAFTER RESET INDEX:\n", df.columns)