import time
import datetime
import pandas as pd
from SmartApi import SmartConnect
import pyotp

# ========================================================================
# CONFIG
# ========================================================================

API_KEY = "JRyUUxSU"
CLIENT_ID = "K339542"
PIN = "0586"
TOTP_SECRET = "LRWKXRNC7RVJI7TV7QJV753FBM"

NIFTY_TOKEN = "99926000"
BANKNIFTY_TOKEN = "99926009"

# ========================================================================
# LOGIN
# ========================================================================

def angel_login():
    try:
        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()

        session = obj.generateSession(CLIENT_ID, PIN, totp)

        if session.get("status") != True:
            raise Exception(f"Login failed. Response: {session}")

        print("LOGIN SUCCESS:", session["data"]["clientcode"])
        return obj

    except Exception as e:
        print("LOGIN ERROR:", e)
        raise


# ========================================================================
# GET 5-MIN CANDLES (fixed, no calls before 09:21)
# ========================================================================

def get_latest_5min_candles(obj, token):
    now = datetime.datetime.now().time()

    # Do NOT request before the FIRST 5-MIN candle is READY
    if now < datetime.time(9, 21):
        return None

    today = datetime.date.today().strftime("%Y-%m-%d")
    start = f"{today} 09:15"
    end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        hist = obj.getCandleData({
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "FIVE_MINUTE",
            "fromdate": start,
            "todate": end_time,
        })

        if hist["status"] and hist["data"]:
            df = pd.DataFrame(
                hist["data"],
                columns=["time", "open", "high", "low", "close", "volume"],
            )
            df["time"] = pd.to_datetime(df["time"])
            return df

        return None

    except:
        return None


# ========================================================================
# MAIN LOOP
# ========================================================================

def run_paper_orb():
    obj = angel_login()
    print("Starting paper ORB engine... waiting until 09:21 for first candle.")

    nifty_or = None
    bnf_or = None
    nifty_trade_taken = False
    bnf_trade_taken = False

    while True:
        now = datetime.datetime.now()

        if now.time() > datetime.time(15, 20):
            print("Market closed. Exiting bot.")
            break

        # Wait until 9:21
        if now.time() < datetime.time(9, 21):
            print("Waiting for 09:21... (first 5-min candle not ready)")
            time.sleep(5)
            continue

        # Fetch data only AFTER 09:21
        nifty_df = get_latest_5min_candles(obj, NIFTY_TOKEN)
        bnf_df = get_latest_5min_candles(obj, BANKNIFTY_TOKEN)

        if nifty_df is None or bnf_df is None:
            print("No candle data yet after 09:21. Retrying...")
            time.sleep(5)
            continue

        # OR Range: 09:15–09:30
        nifty_or_df = nifty_df[
            (nifty_df["time"].dt.time >= datetime.time(9, 15)) &
            (nifty_df["time"].dt.time <= datetime.time(9, 30))
        ]

        bnf_or_df = bnf_df[
            (bnf_df["time"].dt.time >= datetime.time(9, 15)) &
            (bnf_df["time"].dt.time <= datetime.time(9, 30))
        ]

        # Build OR once
        if nifty_or is None and len(nifty_or_df) >= 2:
            nifty_or = (nifty_or_df["high"].max(), nifty_or_df["low"].min())
            print(f"[NIFTY] OR = HIGH {nifty_or[0]} / LOW {nifty_or[1]}")

        if bnf_or is None and len(bnf_or_df) >= 2:
            bnf_or = (bnf_or_df["high"].max(), bnf_or_df["low"].min())
            print(f"[BANKNIFTY] OR = HIGH {bnf_or[0]} / LOW {bnf_or[1]}")

        # Wait until OR is ready
        if nifty_or is None or bnf_or is None:
            time.sleep(5)
            continue

        # Latest candle
        latest_n = nifty_df.iloc[-1]
        latest_b = bnf_df.iloc[-1]

        # NIFTY entry
        if not nifty_trade_taken:
            if latest_n["close"] > nifty_or[0]:
                print(f"[NIFTY LONG] Breakout at {latest_n['close']}")
                nifty_trade_taken = True
            elif latest_n["close"] < nifty_or[1]:
                print(f"[NIFTY SHORT] Breakdown at {latest_n['close']}")
                nifty_trade_taken = True

        # BANKNIFTY entry
        if not bnf_trade_taken:
            if latest_b["close"] > bnf_or[0]:
                print(f"[BANKNIFTY LONG] Breakout at {latest_b['close']}")
                bnf_trade_taken = True
            elif latest_b["close"] < bnf_or[1]:
                print(f"[BANKNIFTY SHORT] Breakdown at {latest_b['close']}")
                bnf_trade_taken = True

        time.sleep(5)


# ========================================================================
# RUN
# ========================================================================

if __name__ == "__main__":
    run_paper_orb()
