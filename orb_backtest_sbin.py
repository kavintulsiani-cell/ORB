import pandas as pd
from datetime import time

# =============================
# CONFIG
# =============================
CSV_FILE = "SBIN_5min.csv"

ORB_START = time(9, 15)
ORB_END = time(10, 15)
TIME_EXIT = time(15, 15)

INITIAL_SL_PCT = 0.005 # 0.5% SL from OR


# =============================
# LOAD DATA
# =============================
df = pd.read_csv(CSV_FILE)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)


# =============================
# BACKTEST
# =============================
trades = []

current_trade = None
or_high = None
or_low = None
or_ready = False
t1_hit = False
trail_sl = None

for idx, row in df.iterrows():
    ts = row["timestamp"].time()
    open_ = row["open"]
    high = row["high"]
    low = row["low"]
    close = row["close"]

    # -------------------------------------
    # BUILD OPENING RANGE (9:15 - 10:15)
    # -------------------------------------
    if ORB_START <= ts <= ORB_END:
        if or_high is None or high > or_high:
            or_high = high
        if or_low is None or low < or_low:
            or_low = low
        continue

    # Mark OR ready after 10:15
    if ts > ORB_END and not or_ready:
        or_ready = True
        continue

    if not or_ready:
        continue

    # =====================================
    # ENTRY LOGIC
    # =====================================
    if current_trade is None:

        # LONG ENTRY
        if high > or_high and close > or_high:
            current_trade = {
                "direction": "LONG",
                "entry_time": row["timestamp"],
                "entry_price": close,
                "initial_sl": or_high * (1 - INITIAL_SL_PCT),
                "or_level": or_high,
            }
            t1_hit = False
            trail_sl = None
            continue

        # SHORT ENTRY
        if low < or_low and close < or_low:
            current_trade = {
                "direction": "SHORT",
                "entry_time": row["timestamp"],
                "entry_price": close,
                "initial_sl": or_low * (1 + INITIAL_SL_PCT),
                "or_level": or_low,
            }
            t1_hit = False
            trail_sl = None
            continue


    # =====================================
    # EXIT LOGIC
    # =====================================
    else:
        direction = current_trade["direction"]

        # TIME EXIT
        if ts >= TIME_EXIT:
            current_trade["exit_time"] = row["timestamp"]
            current_trade["exit_price"] = close
            current_trade["reason"] = "TIME EXIT"
            trades.append(current_trade)
            current_trade = None
            continue

        # BEFORE T1 HIT
        if not t1_hit:

            # INITIAL SL HIT
            if direction == "LONG" and low <= current_trade["initial_sl"]:
                current_trade["exit_time"] = row["timestamp"]
                current_trade["exit_price"] = current_trade["initial_sl"]
                current_trade["reason"] = "INITIAL SL"
                trades.append(current_trade)
                current_trade = None
                continue

            if direction == "SHORT" and high >= current_trade["initial_sl"]:
                current_trade["exit_time"] = row["timestamp"]
                current_trade["exit_price"] = current_trade["initial_sl"]
                current_trade["reason"] = "INITIAL SL"
                trades.append(current_trade)
                current_trade = None
                continue

            # T1 HIT (price touches OR)
            if direction == "LONG" and high >= current_trade["or_level"]:
                t1_hit = True
                trail_sl = low # previous candle low
                continue

            if direction == "SHORT" and low <= current_trade["or_level"]:
                t1_hit = True
                trail_sl = high # previous candle high
                continue

        # AFTER T1 HIT → TRAILING STOP
        else:
            # Long: new trailing SL = previous candle low
            if direction == "LONG":
                new_sl = low
                if trail_sl is None or new_sl < trail_sl:
                    trail_sl = new_sl

                if low <= trail_sl:
                    current_trade["exit_time"] = row["timestamp"]
                    current_trade["exit_price"] = trail_sl
                    current_trade["reason"] = "TRAIL SL"
                    trades.append(current_trade)
                    current_trade = None
                    continue

            # Short: new trailing SL = previous candle high
            if direction == "SHORT":
                new_sl = high
                if trail_sl is None or new_sl > trail_sl:
                    trail_sl = new_sl

                if high >= trail_sl:
                    current_trade["exit_time"] = row["timestamp"]
                    current_trade["exit_price"] = trail_sl
                    current_trade["reason"] = "TRAIL SL"
                    trades.append(current_trade)
                    current_trade = None
                    continue


# =============================
# RESULTS
# =============================
print("\n====== TRADES ======\n")
for t in trades:
    print(t)

pnl = []
for t in trades:
    if t["direction"] == "LONG":
        pnl.append(t["exit_price"] - t["entry_price"])
    else:
        pnl.append(t["entry_price"] - t["exit_price"])

print("\n===== SUMMARY =====")
print("Total trades:", len(trades))
wins = sum(1 for x in pnl if x > 0)
loss = len(pnl) - wins
print("Wins:", wins)
print("Losses:", loss)
if len(pnl) > 0:
    print("Win rate:", f"{wins / len(pnl) * 100:.2f}%")
    print("Total PnL:", sum(pnl))
    print("Avg per trade:", sum(pnl) / len(pnl))
