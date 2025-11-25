import time
import datetime
import pandas as pd
from smartapi import SmartConnect
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
    obj = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    data = obj.generateSession(CLIENT_ID, PIN, totp)
    if "token" in data:
        print("LOGIN SUCCESS:", CLIENT_ID)
    else:
        raise Exception("Login failed:", data)
    return obj

# ========================================================================
# GET 5-MIN CANDLES (after 9:15 ONLY)
# ========================================================================

def get_latest_5min_candles(obj, token):
    now = datetime.datetime.now().time()

    # DO NOT FETCH BEFORE 9:15 → PREVENTS ALL ERRORS
    if now < datetime.time(9, 15):
        return None

    # Define time range for today's candles
    today = datetime.date.today().strftime("%Y-%m-%d")
    start = f"{today} 09:15"
    end_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        hist = obj.getCandleData(
            {
                "exchange": "NSE",
                "symboltoken": token,
                "interval": "FIVE_MINUTE",
                "fromdate": start,
                "todate": end_time,
            }
        )
        if hist["status"] and hist["data"]:
            df = pd.DataFrame(
                hist["data"],
                columns=["time", "open", "high", "low", "close", "volume"],
            )
            df["time"] = pd.to_datetime(df["time"])
            return df
        return None

    except Exception:
        return None # VERY IMPORTANT — do NOT show errors before 9:15


# ========================================================================
# MAIN STRATEGY LOOP (PAPER TRADING)
# ========================================================================

def run_paper_orb():
    obj = angel_login()
    print("Starting paper ORB engine for NIFTY & BANKNIFTY...")
    print("Waiting for 9:15... this will run until 15:20.")

    nifty_or = None
    bnf_or = None
    nifty_trade_taken = False
    bnf_trade_taken = False

    while True:
        now = datetime.datetime.now()

        # Stop after 3:20 PM
        if now.time() > datetime.time(15, 20):
            print("Market over. Exiting paper engine.")
            break

        # Wait until 9:15
        if now.time() < datetime.time(9, 15):
            print("⏳ Waiting for 9:15... no candle data yet.")
            time.sleep(10)
            continue

        # Fetch candles AFTER 9:15
        nifty_df = get_latest_5min_candles(obj, NIFTY_TOKEN)
        bnf_df = get_latest_5min_candles(obj, BANKNIFTY_TOKEN)

        if nifty_df is None or bnf_df is None:
            print("⚠ No candle data yet (but after 9:15). Waiting...")
            time.sleep(5)
            continue

        # ===============================
        # BUILD OPENING RANGE 9:15–9:30
        # ===============================
        nifty_or_df = nifty_df[(nifty_df["time"].dt.time >= datetime.time(9, 15)) &
                               (nifty_df["time"].dt.time <= datetime.time(9, 30))]

        bnf_or_df = bnf_df[(bnf_df["time"].dt.time >= datetime.time(9, 15)) &
                           (bnf_df["time"].dt.time <= datetime.time(9, 30))]

        if nifty_or is None and len(nifty_or_df) >= 2:
            nifty_or = (nifty_or_df["high"].max(), nifty_or_df["low"].min())
            print(f"[NIFTY] OR built → HIGH={nifty_or[0]} LOW={nifty_or[1]}")

        if bnf_or is None and len(bnf_or_df) >= 2:
            bnf_or = (bnf_or_df["high"].max(), bnf_or_df["low"].min())
            print(f"[BANKNIFTY] OR built → HIGH={bnf_or[0]} LOW={bnf_or[1]}")


        # If OR not built yet, wait
        if nifty_or is None or bnf_or is None:
            time.sleep(5)
            continue

        # ======================================
        # CHECK BREAKOUT AFTER 9:30
        # ======================================
        latest_n = nifty_df.iloc[-1]
        latest_b = bnf_df.iloc[-1]

        # NIFTY Breakout
        if not nifty_trade_taken:
            if latest_n["close"] > nifty_or[0]:
                print(f"[NIFTY LONG] Breakout above OR HIGH at {latest_n['close']}")
                nifty_trade_taken = True

            elif latest_n["close"] < nifty_or[1]:
                print(f"[NIFTY SHORT] Breakdown below OR LOW at {latest_n['close']}")
                nifty_trade_taken = True

        # BANKNIFTY Breakout
        if not bnf_trade_taken:
            if latest_b["close"] > bnf_or[0]:
                print(f"[BANKNIFTY LONG] Breakout above OR HIGH at {latest_b['close']}")
                bnf_trade_taken = True

            elif latest_b["close"] < bnf_or[1]:
                print(f"[BANKNIFTY SHORT] Breakdown below OR LOW at {latest_b['close']}")
                bnf_trade_taken = True

        time.sleep(5)


# ========================================================================
# RUN
# ========================================================================

if __name__ == "__main__":
    run_paper_orb()
