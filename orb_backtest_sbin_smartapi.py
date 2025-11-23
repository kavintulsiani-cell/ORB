import pandas as pd
from datetime import time

CSV_FILE = "ICICIBANK_5min_SmartAPI.csv"

# Session config
MARKET_START = time(9, 15)
ORB_END = time(10, 15)
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

        # Restrict to regular market session
        day_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START) &
            (day_df["timestamp"].dt.time <= EOD_EXIT)
        ]
        if day_df.empty:
            continue

        # -------- Opening Range 9:15–10:15 --------
        or_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START) &
            (day_df["timestamp"].dt.time <= ORB_END)
        ]
        if or_df.empty:
            continue

        or_high = or_df["high"].max()
        or_low = or_df["low"].min()
        or_range = or_high - or_low

        # Targets based on OR range (for info)
        long_t1 = or_high + or_range
        short_t1 = or_low - or_range

        # Initial SL = 1% buffer from OR levels
        long_sl_init = or_high * (1 - 0.01) # 1% below OR high
        short_sl_init = or_low * (1 + 0.01) # 1% above OR low

        # TSL activates only after 1.5x OR move
        long_tsl_trigger = or_high + 1.5 * or_range
        short_tsl_trigger = or_low - 1.5 * or_range

        in_trade = False
        direction = None
        entry_price = None
        entry_time = None
        sl = None
        tsl_active = False
        prev_low = None
        prev_high = None

        after_orb_df = day_df[day_df["timestamp"].dt.time > ORB_END]
        if after_orb_df.empty:
            continue

        for i, row in after_orb_df.iterrows():
            ts = row["timestamp"]
            t = ts.time()
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # If in a position, manage it first
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
                    # 1) Hard SL
                    if l <= sl:
                        trades.append({
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": sl,
                            "reason": "SL"
                        })
                        in_trade = False
                        break

                    # 2) Activate TSL only after 1.5x OR move
                    if (not tsl_active) and h >= long_tsl_trigger:
                        tsl_active = True

                    # 3) If TSL active, exit on close below prev low
                    if tsl_active and prev_low is not None and c < prev_low:
                        trades.append({
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": c,
                            "reason": "TSL_prev_low"
                        })
                        in_trade = False
                        break

                elif direction == "SHORT":
                    if h >= sl:
                        trades.append({
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": sl,
                            "reason": "SL"
                        })
                        in_trade = False
                        break

                    if (not tsl_active) and l <= short_tsl_trigger:
                        tsl_active = True

                    if tsl_active and prev_high is not None and c > prev_high:
                        trades.append({
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": c,
                            "reason": "TSL_prev_high"
                        })
                        in_trade = False
                        break

                # Update for next bar
                prev_low = l
                prev_high = h
                continue

            # -------- No trade open: look for first breakout of the day --------
            # Only one completed trade per day
            if any(tr["date"] == day for tr in trades):
                break

            # LONG breakout
            if c > or_high:
                in_trade = True
                direction = "LONG"
                entry_price = c
                entry_time = ts
                sl = long_sl_init
                tsl_active = False
                prev_low = l
                prev_high = h
                continue

            # SHORT breakout
            if c < or_low:
                in_trade = True
                direction = "SHORT"
                entry_price = c
                entry_time = ts
                sl = short_sl_init
                tsl_active = False
                prev_low = l
                prev_high = h
                continue

            prev_low = l
            prev_high = h

        # If still in trade at end of data for the day
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


def summarize(trades):
    if not trades:
        print("No trades generated.")
        return

    pnl_list = []
    for t in trades:
        if t["direction"] == "LONG":
            pnl = t["exit_price"] - t["entry_price"]
        else:
            pnl = t["entry_price"] - t["exit_price"]
        t["pnl"] = pnl
        pnl_list.append(pnl)

    print("\n===== SAMPLE TRADES =====")
    for t in trades[:10]:
        print(t)

    total_trades = len(trades)
    wins = sum(1 for p in pnl_list if p > 0)
    losses = sum(1 for p in pnl_list if p < 0)

    print("\n===== SUMMARY =====")
    print("Total trades :", total_trades)
    print("Wins :", wins)
    print("Losses :", losses)
    if total_trades > 0:
        print(f"Win rate : {wins/total_trades*100:.2f}%")
        print(f"Total PnL : {sum(pnl_list):.2f} (in underlying points)")
        print(f"Avg / trade : {sum(pnl_list)/total_trades:.2f}")


if __name__ == "__main__":
    df = load_data(CSV_FILE)
    trades = backtest_orb(df)
    summarize(trades)
