import time
from datetime import datetime, date, time as dtime, timedelta
import csv

import pyotp
from SmartApi import SmartConnect
import pandas as pd

# ========= CONFIG =========

API_KEY = "JRyUUxSU"
CLIENT_ID = "K339542"
PIN = "0586"
TOTP_SECRET = "LRWKXRNC7RVJI7TV7QJV753FBM"

EXCHANGE = "NSE"

# SmartAPI index tokens (adjust if needed)
INSTRUMENTS = {
    "NIFTY": {
        "token": "99926000",
        "t1": 40, # points
        "t2": 80,
    },
    "BANKNIFTY": {
        "token": "99926009",
        "t1": 120,
        "t2": 250,
    },
}

MARKET_START = dtime(9, 15)
ORB_END = dtime(9, 30)
EOD_EXIT = dtime(15, 15)

# How often to poll SmartAPI for candles (in seconds)
POLL_SECONDS = 15 # 15 sec is fine for 5-min candles


# ========= SMARTAPI LOGIN =========

def login_smartapi():
    smart = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    data = smart.generateSession(CLIENT_ID, PIN, totp)
    print("LOGIN SUCCESS:", data.get("data", {}).get("clientcode"))
    return smart


# ========= UTILS =========

def today_str():
    return date.today().strftime("%Y-%m-%d")


def get_today_candles_5m(smart, token: str):
    """Fetch today's 5-min candles for the given token."""
    now = datetime.now()
    start = datetime.combine(date.today(), MARKET_START)
    # some brokers require fromdate <= todate
    params = {
        "exchange": EXCHANGE,
        "symboltoken": token,
        "interval": "FIVE_MINUTE",
        "fromdate": start.strftime("%Y-%m-%d %H:%M"),
        "todate": now.strftime("%Y-%m-%d %H:%M"),
    }
    data = smart.getCandleData(params)
    candles = data.get("data")
    if not candles:
        return None
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def init_daily_csv():
    fname = f"paper_orb_trades_{today_str()}.csv"
    # create with header if not exists
    try:
        with open(fname, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "instrument", "date",
                "direction",
                "entry_time", "entry_price",
                "exit_time", "exit_price",
                "reason", "pnl"
            ])
    except FileExistsError:
        pass
    return fname


def append_trade_to_csv(fname, trade):
    with open(fname, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            trade["instrument"],
            trade["date"],
            trade["direction"],
            trade["entry_time"],
            trade["entry_price"],
            trade["exit_time"],
            trade["exit_price"],
            trade["reason"],
            trade["pnl"],
        ])


# ========= STATE PER INSTRUMENT =========

def init_state():
    state = {}
    for name in INSTRUMENTS.keys():
        state[name] = {
            "or_high": None,
            "or_low": None,
            "or_done": False,
            "in_trade": False,
            "direction": None,
            "entry_price": None,
            "entry_time": None,
            "size_remain": 0.0,
            "realized_pnl": 0.0,
            "reached_t1": False,
            "prev_low": None,
            "prev_high": None,
            "be_sl": None,
            "last_candle_time": None,
            "trade_closed": False, # only 1 trade per day
        }
    return state


# ========= ORB PAPER ENGINE =========

def process_new_candle(name, cfg, row, st, csv_fname):
    """
    Process a newly completed candle for one instrument.
    row: pandas Series with timestamp, open, high, low, close, volume
    st: state dict for that instrument
    """
    ts = row["timestamp"]
    t = ts.time()
    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
    day = ts.date()
    t1_points = cfg["t1"]
    t2_points = cfg["t2"]

    # 1) Build Opening Range 9:15–9:30
    if not st["or_done"]:
        if MARKET_START <= t <= ORB_END:
            if st["or_high"] is None:
                st["or_high"] = h
                st["or_low"] = l
            else:
                st["or_high"] = max(st["or_high"], h)
                st["or_low"] = min(st["or_low"], l)
        if t > ORB_END and st["or_high"] is not None and st["or_low"] is not None:
            st["or_done"] = True
            print(f"[{name}] ORB completed. OR_HIGH={st['or_high']:.2f}, OR_LOW={st['or_low']:.2f}")
        return

    # 2) Manage open trade (if any)
    if st["in_trade"]:
        # EOD exit
        if t >= EOD_EXIT:
            exit_price = c
            pnl_add = (st["size_remain"] * (exit_price - st["entry_price"])
                       if st["direction"] == "LONG"
                       else st["size_remain"] * (st["entry_price"] - exit_price))
            st["realized_pnl"] += pnl_add
            trade = {
                "instrument": name,
                "date": day,
                "direction": st["direction"],
                "entry_time": st["entry_time"],
                "entry_price": st["entry_price"],
                "exit_time": ts,
                "exit_price": exit_price,
                "reason": "EOD",
                "pnl": st["realized_pnl"],
            }
            print("[EOD EXIT]", trade)
            append_trade_to_csv(csv_fname, trade)
            st["in_trade"] = False
            st["trade_closed"] = True
            return

        # BEFORE T1
        if not st["reached_t1"]:
            or_high = st["or_high"]
            or_low = st["or_low"]
            if st["direction"] == "LONG":
                # SL at OR low
                if l <= or_low:
                    exit_price = or_low
                    pnl_add = st["size_remain"] * (exit_price - st["entry_price"])
                    st["realized_pnl"] += pnl_add
                    trade = {
                        "instrument": name,
                        "date": day,
                        "direction": st["direction"],
                        "entry_time": st["entry_time"],
                        "entry_price": st["entry_price"],
                        "exit_time": ts,
                        "exit_price": exit_price,
                        "reason": "SL_BEFORE_T1",
                        "pnl": st["realized_pnl"],
                    }
                    print("[SL BEFORE T1]", trade)
                    append_trade_to_csv(csv_fname, trade)
                    st["in_trade"] = False
                    st["trade_closed"] = True
                    return

                t1_price = st["entry_price"] + t1_points
                t2_price = st["entry_price"] + t2_points

                # T2 same bar (implies T1 also hit)
                if h >= t2_price:
                    st["realized_pnl"] += 0.5 * (t1_price - st["entry_price"])
                    st["realized_pnl"] += 0.5 * (t2_price - st["entry_price"])
                    trade = {
                        "instrument": name,
                        "date": day,
                        "direction": st["direction"],
                        "entry_time": st["entry_time"],
                        "entry_price": st["entry_price"],
                        "exit_time": ts,
                        "exit_price": t2_price,
                        "reason": "T1+T2_SAME_BAR",
                        "pnl": st["realized_pnl"],
                    }
                    print("[T1+T2 SAME BAR]", trade)
                    append_trade_to_csv(csv_fname, trade)
                    st["in_trade"] = False
                    st["trade_closed"] = True
                    return

                # Only T1 hit
                if h >= t1_price:
                    st["realized_pnl"] += 0.5 * (t1_price - st["entry_price"])
                    st["size_remain"] = 0.5
                    st["reached_t1"] = True
                    st["be_sl"] = st["entry_price"]
                    print(f"[{name}] T1 hit. Booked 50%. BE SL set at {st['be_sl']:.2f}")
                    st["prev_low"] = l
                    st["prev_high"] = h
                    return

            else: # SHORT
                if h >= or_high:
                    exit_price = or_high
                    pnl_add = st["size_remain"] * (st["entry_price"] - exit_price)
                    st["realized_pnl"] += pnl_add
                    trade = {
                        "instrument": name,
                        "date": day,
                        "direction": st["direction"],
                        "entry_time": st["entry_time"],
                        "entry_price": st["entry_price"],
                        "exit_time": ts,
                        "exit_price": exit_price,
                        "reason": "SL_BEFORE_T1",
                        "pnl": st["realized_pnl"],
                    }
                    print("[SL BEFORE T1]", trade)
                    append_trade_to_csv(csv_fname, trade)
                    st["in_trade"] = False
                    st["trade_closed"] = True
                    return

                t1_price = st["entry_price"] - t1_points
                t2_price = st["entry_price"] - t2_points

                if l <= t2_price:
                    st["realized_pnl"] += 0.5 * (st["entry_price"] - t1_price)
                    st["realized_pnl"] += 0.5 * (st["entry_price"] - t2_price)
                    trade = {
                        "instrument": name,
                        "date": day,
                        "direction": st["direction"],
                        "entry_time": st["entry_time"],
                        "entry_price": st["entry_price"],
                        "exit_time": ts,
                        "exit_price": t2_price,
                        "reason": "T1+T2_SAME_BAR",
                        "pnl": st["realized_pnl"],
                    }
                    print("[T1+T2 SAME BAR]", trade)
                    append_trade_to_csv(csv_fname, trade)
                    st["in_trade"] = False
                    st["trade_closed"] = True
                    return

                if l <= t1_price:
                    st["realized_pnl"] += 0.5 * (st["entry_price"] - t1_price)
                    st["size_remain"] = 0.5
                    st["reached_t1"] = True
                    st["be_sl"] = st["entry_price"]
                    print(f"[{name}] T1 hit. Booked 50%. BE SL set at {st['be_sl']:.2f}")
                    st["prev_low"] = l
                    st["prev_high"] = h
                    return

            st["prev_low"] = l
            st["prev_high"] = h
            return

        # AFTER T1: BE SL + candle TSL + T2
        if st["direction"] == "LONG":
            t2_price = st["entry_price"] + t2_points

            # T2 hit?
            if h >= t2_price:
                exit_price = t2_price
                st["realized_pnl"] += st["size_remain"] * (exit_price - st["entry_price"])
                trade = {
                    "instrument": name,
                    "date": day,
                    "direction": st["direction"],
                    "entry_time": st["entry_time"],
                    "entry_price": st["entry_price"],
                    "exit_time": ts,
                    "exit_price": exit_price,
                    "reason": "T2",
                    "pnl": st["realized_pnl"],
                }
                print("[T2 EXIT]", trade)
                append_trade_to_csv(csv_fname, trade)
                st["in_trade"] = False
                st["trade_closed"] = True
                return

            # Candle TSL
            if st["prev_low"] is not None and c < st["prev_low"]:
                exit_price = c
                st["realized_pnl"] += st["size_remain"] * (exit_price - st["entry_price"])
                trade = {
                    "instrument": name,
                    "date": day,
                    "direction": st["direction"],
                    "entry_time": st["entry_time"],
                    "entry_price": st["entry_price"],
                    "exit_time": ts,
                    "exit_price": exit_price,
                    "reason": "TSL_PREV_LOW",
                    "pnl": st["realized_pnl"],
                }
                print("[TSL PREV LOW EXIT]", trade)
                append_trade_to_csv(csv_fname, trade)
                st["in_trade"] = False
                st["trade_closed"] = True
                return

            # BE SL
            if st["be_sl"] is not None and l <= st["be_sl"]:
                exit_price = st["be_sl"]
                st["realized_pnl"] += st["size_remain"] * (exit_price - st["entry_price"])
                trade = {
                    "instrument": name,
                    "date": day,
                    "direction": st["direction"],
                    "entry_time": st["entry_time"],
                    "entry_price": st["entry_price"],
                    "exit_time": ts,
                    "exit_price": exit_price,
                    "reason": "SL_BE",
                    "pnl": st["realized_pnl"],
                }
                print("[BE SL EXIT]", trade)
                append_trade_to_csv(csv_fname, trade)
                st["in_trade"] = False
                st["trade_closed"] = True
                return

        else: # SHORT
            t2_price = st["entry_price"] - t2_points

            if l <= t2_price:
                exit_price = t2_price
                st["realized_pnl"] += st["size_remain"] * (st["entry_price"] - exit_price)
                trade = {
                    "instrument": name,
                    "date": day,
                    "direction": st["direction"],
                    "entry_time": st["entry_time"],
                    "entry_price": st["entry_price"],
                    "exit_time": ts,
                    "exit_price": exit_price,
                    "reason": "T2",
                    "pnl": st["realized_pnl"],
                }
                print("[T2 EXIT]", trade)
                append_trade_to_csv(csv_fname, trade)
                st["in_trade"] = False
                st["trade_closed"] = True
                return

            if st["prev_high"] is not None and c > st["prev_high"]:
                exit_price = c
                st["realized_pnl"] += st["size_remain"] * (st["entry_price"] - exit_price)
                trade = {
                    "instrument": name,
                    "date": day,
                    "direction": st["direction"],
                    "entry_time": st["entry_time"],
                    "entry_price": st["entry_price"],
                    "exit_time": ts,
                    "exit_price": exit_price,
                    "reason": "TSL_PREV_HIGH",
                    "pnl": st["realized_pnl"],
                }
                print("[TSL PREV HIGH EXIT]", trade)
                append_trade_to_csv(csv_fname, trade)
                st["in_trade"] = False
                st["trade_closed"] = True
                return

            if st["be_sl"] is not None and h >= st["be_sl"]:
                exit_price = st["be_sl"]
                st["realized_pnl"] += st["size_remain"] * (st["entry_price"] - exit_price)
                trade = {
                    "instrument": name,
                    "date": day,
                    "direction": st["direction"],
                    "entry_time": st["entry_time"],
                    "entry_price": st["entry_price"],
                    "exit_time": ts,
                    "exit_price": exit_price,
                    "reason": "SL_BE",
                    "pnl": st["realized_pnl"],
                }
                print("[BE SL EXIT]", trade)
                append_trade_to_csv(csv_fname, trade)
                st["in_trade"] = False
                st["trade_closed"] = True
                return

        st["prev_low"] = l
        st["prev_high"] = h
        return

    # 3) No open trade: look for first breakout (only 1/day)
    if st["trade_closed"]:
        return # already traded and closed

    if t <= ORB_END:
        return # still inside OR window

    or_high = st["or_high"]
    or_low = st["or_low"]
    if or_high is None or or_low is None:
        return

    # Long breakout
    if c > or_high:
        st["in_trade"] = True
        st["direction"] = "LONG"
        st["entry_price"] = c
        st["entry_time"] = ts
        st["size_remain"] = 1.0 # we treat 1 unit; real lots mapping later
        st["realized_pnl"] = 0.0
        st["reached_t1"] = False
        st["prev_low"] = l
        st["prev_high"] = h
        st["be_sl"] = None
        print(f"[{name}] LONG entry at {c:.2f} at {ts}")
        return

    # Short breakout
    if c < or_low:
        st["in_trade"] = True
        st["direction"] = "SHORT"
        st["entry_price"] = c
        st["entry_time"] = ts
        st["size_remain"] = 1.0
        st["realized_pnl"] = 0.0
        st["reached_t1"] = False
        st["prev_low"] = l
        st["prev_high"] = h
        st["be_sl"] = None
        print(f"[{name}] SHORT entry at {c:.2f} at {ts}")
        return


# ========= MAIN LOOP =========

def main():
    smart = login_smartapi()
    csv_fname = init_daily_csv()
    state = init_state()

    print("Starting paper ORB engine for NIFTY & BANKNIFTY...")
    print("This will run until after 15:15 India time.")

    while True:
        now = datetime.now()
        # Stop after EOD + buffer
        if now.time() > dtime(15, 20):
            print("Day complete. Exiting bot loop.")
            break

        # Only start active work from 9:00
        if now.time() < dtime(9, 0):
            time.sleep(30)
            continue

        for name, cfg in INSTRUMENTS.items():
            token = cfg["token"]
            df = get_today_candles_5m(smart, token)
            if df is None or df.empty:
                print(f"[{name}] No candle data yet")
                continue

            # Process only *new* candles since last time
            latest = df.iloc[-1]
            latest_ts = latest["timestamp"]
            latest_time = latest_ts.time()

            # Ignore candles before market start
            if latest_time < MARKET_START:
                continue

            st = state[name]
            if st["last_candle_time"] is not None and latest_ts <= st["last_candle_time"]:
                continue # already processed

            st["last_candle_time"] = latest_ts
            print(f"\n[{name}] New candle: {latest_ts}, O={latest['open']}, H={latest['high']}, "
                  f"L={latest['low']}, C={latest['close']}")

            process_new_candle(name, cfg, latest, st, csv_fname)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
