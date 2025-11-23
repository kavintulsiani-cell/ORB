import pandas as pd
from datetime import time

# Change this to "BANKNIFTY_5min_SmartAPI.csv" to test Banknifty
CSV_FILE = "NIFTY_5min_SmartAPI.csv"

MARKET_START = time(9, 15)
ORB_END = time(9, 30) # first 15 minutes
EOD_EXIT = time(15, 15)


def load_data(path):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def backtest_orb(df):
    trades = []

    df["date"] = df["timestamp"].dt.date

    for day, day_df in df.groupby("date"):
        day_df = day_df.sort_values("timestamp").reset_index(drop=True)

        # Regular session only
        day_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START) &
            (day_df["timestamp"].dt.time <= EOD_EXIT)
        ]
        if day_df.empty:
            continue

        # ---- Opening Range: 9:15 to 9:30 (15 mins) ----
        or_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START) &
            (day_df["timestamp"].dt.time <= ORB_END)
        ]
        if or_df.empty:
            continue

        or_high = or_df["high"].max()
        or_low = or_df["low"].min()

        in_trade = False
        direction = None
        entry_price = None
        entry_time = None

        after_orb_df = day_df[day_df["timestamp"].dt.time > ORB_END]
        if after_orb_df.empty:
            continue

        for _, row in after_orb_df.iterrows():
            ts = row["timestamp"]
            t = ts.time()
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # Manage open trade
            if in_trade:
                # EOD exit
                if t >= EOD_EXIT:
                    trades.append({
                        "date": day,
                        "direction": direction,
                        "entry_time": entry_time,
                        "entry_price": entry_price,
                        "exit_time": ts,
                        "exit_price": c,
                        "reason": "EOD"
                    })
                    in_trade = False
                    break

                if direction == "LONG":
                    # SL at OR low
                    if l <= or_low:
                        trades.append({
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": or_low,
                            "reason": "SL"
                        })
                        in_trade = False
                        break
                else: # SHORT
                    if h >= or_high:
                        trades.append({
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": or_high,
                            "reason": "SL"
                        })
                        in_trade = False
                        break

                continue # if still in trade, go next candle

            # ----- No trade yet: look for first breakout -----
            # Only one trade per day
            if any(tr["date"] == day for tr in trades):
                break

            # Long breakout
            if c > or_high:
                in_trade = True
                direction = "LONG"
                entry_price = c
                entry_time = ts
                continue

            # Short breakout
            if c < or_low:
                in_trade = True
                direction = "SHORT"
                entry_price = c
                entry_time = ts
                continue

        # If still in trade at the very end without hitting EOD_EXIT exactly
        if in_trade:
            last_row = after_orb_df.iloc[-1]
            trades.append({
                "date": day,
                "direction": direction,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "exit_time": last_row["timestamp"],
                "exit_price": last_row["close"],
                "reason": "DAY_END_FALLBACK"
            })
            in_trade = False

    return trades


def summarize(trades, label="NIFTY"):
    if not trades:
        print(f"No trades generated for {label}.")
        return

    pnl_list = []
    for t in trades:
        if t["direction"] == "LONG":
            pnl = t["exit_price"] - t["entry_price"]
        else:
            pnl = t["entry_price"] - t["exit_price"]
        t["pnl"] = pnl
        pnl_list.append(pnl)

    print(f"\n===== SAMPLE TRADES ({label}) =====")
    for t in trades[:10]:
        print(t)

    total_trades = len(trades)
    wins = sum(1 for p in pnl_list if p > 0)
    losses = sum(1 for p in pnl_list if p < 0)

    print(f"\n===== SUMMARY ({label}) =====")
    print("Total trades :", total_trades)
    print("Wins :", wins)
    print("Losses :", losses)
    if total_trades > 0:
        print(f"Win rate : {wins/total_trades*100:.2f}%")
        print(f"Total PnL : {sum(pnl_list):.2f} (index points)")
        print(f"Avg / trade : {sum(pnl_list)/total_trades:.2f}")


if __name__ == "__main__":
    df = load_data(CSV_FILE)
    label = "NIFTY" if "NIFTY" in CSV_FILE.upper() else "BANKNIFTY"
    trades = backtest_orb(df)
    summarize(trades, label)
