import pandas as pd
from datetime import time

INSTRUMENTS = {
    "NIFTY": {
        "csv": "NIFTY_5min_SmartAPI.csv",
        "t1": 40,
        "t2": 80,
    },
    "BANKNIFTY": {
        "csv": "BANKNIFTY_5min_SmartAPI.csv",
        "t1": 120,
        "t2": 250,
    },
}

MARKET_START = time(9, 15)
ORB_END = time(9, 30)
EOD_EXIT = time(15, 15)


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def backtest_orb(df: pd.DataFrame, t1_points: float, t2_points: float, label: str):
    trades = []
    df = df.copy()
    df["date"] = df["timestamp"].dt.date

    for day, day_df in df.groupby("date"):
        day_df = day_df.sort_values("timestamp").reset_index(drop=True)

        # Restrict to normal market hours
        day_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START)
            & (day_df["timestamp"].dt.time <= EOD_EXIT)
        ]
        if day_df.empty:
            continue

        # ---- Build Opening Range (9:15–9:30) ----
        or_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START)
            & (day_df["timestamp"].dt.time <= ORB_END)
        ]
        if or_df.empty:
            continue

        or_high = or_df["high"].max()
        or_low = or_df["low"].min()

        in_trade = False
        direction = None
        entry_price = None
        entry_time = None
        size_remain = 0.0
        realized_pnl = 0.0
        reached_t1 = False
        prev_low = None
        prev_high = None

        after_orb_df = day_df[day_df["timestamp"].dt.time > ORB_END]
        if after_orb_df.empty:
            continue

        for _, row in after_orb_df.iterrows():
            ts = row["timestamp"]
            t = ts.time()
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # ------------- Manage Open Trade -------------
            if in_trade:
                # Hard time exit
                if t >= EOD_EXIT:
                    exit_price = c
                    realized_pnl += (
                        size_remain * (exit_price - entry_price)
                        if direction == "LONG"
                        else size_remain * (entry_price - exit_price)
                    )
                    trades.append(
                        {
                            "instrument": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "EOD",
                            "pnl": realized_pnl,
                        }
                    )
                    in_trade = False
                    break

                if not reached_t1:
                    # --- Before T1: only OR SL & check T1/T2 ---
                    if direction == "LONG":
                        # SL at OR low
                        if l <= or_low:
                            exit_price = or_low
                            realized_pnl += size_remain * (
                                exit_price - entry_price
                            )
                            trades.append(
                                {
                                    "instrument": label,
                                    "date": day,
                                    "direction": direction,
                                    "entry_time": entry_time,
                                    "entry_price": entry_price,
                                    "exit_time": ts,
                                    "exit_price": exit_price,
                                    "reason": "SL_BEFORE_T1",
                                    "pnl": realized_pnl,
                                }
                            )
                            in_trade = False
                            break

                        # Check T2 first (can imply T1 also hit)
                        t1_price = entry_price + t1_points
                        t2_price = entry_price + t2_points
                        if h >= t2_price:
                            # 50% at T1, 50% at T2 in same bar
                            realized_pnl += 0.5 * (t1_price - entry_price)
                            realized_pnl += 0.5 * (t2_price - entry_price)
                            trades.append(
                                {
                                    "instrument": label,
                                    "date": day,
                                    "direction": direction,
                                    "entry_time": entry_time,
                                    "entry_price": entry_price,
                                    "exit_time": ts,
                                    "exit_price": t2_price,
                                    "reason": "T1+T2_SAME_BAR",
                                    "pnl": realized_pnl,
                                }
                            )
                            in_trade = False
                            break

                        # Only T1 hit
                        if h >= t1_price:
                            realized_pnl += 0.5 * (t1_price - entry_price)
                            size_remain = 0.5
                            reached_t1 = True
                            # After T1, SL moves to entry (break-even)
                            be_sl = entry_price
                        else:
                            # Nothing more to manage this bar
                            prev_low = l
                            prev_high = h
                            continue

                    else: # SHORT
                        if h >= or_high:
                            exit_price = or_high
                            realized_pnl += size_remain * (
                                entry_price - exit_price
                            )
                            trades.append(
                                {
                                    "instrument": label,
                                    "date": day,
                                    "direction": direction,
                                    "entry_time": entry_time,
                                    "entry_price": entry_price,
                                    "exit_time": ts,
                                    "exit_price": exit_price,
                                    "reason": "SL_BEFORE_T1",
                                    "pnl": realized_pnl,
                                }
                            )
                            in_trade = False
                            break

                        t1_price = entry_price - t1_points
                        t2_price = entry_price - t2_points
                        if l <= t2_price:
                            realized_pnl += 0.5 * (entry_price - t1_price)
                            realized_pnl += 0.5 * (entry_price - t2_price)
                            trades.append(
                                {
                                    "instrument": label,
                                    "date": day,
                                    "direction": direction,
                                    "entry_time": entry_time,
                                    "entry_price": entry_price,
                                    "exit_time": ts,
                                    "exit_price": t2_price,
                                    "reason": "T1+T2_SAME_BAR",
                                    "pnl": realized_pnl,
                                }
                            )
                            in_trade = False
                            break

                        if l <= t1_price:
                            realized_pnl += 0.5 * (entry_price - t1_price)
                            size_remain = 0.5
                            reached_t1 = True
                            be_sl = entry_price
                        else:
                            prev_low = l
                            prev_high = h
                            continue

                    # After this point in the bar, T1 has been reached.
                    # From next bar onwards, we will use BE + candle TSL.
                    prev_low = l
                    prev_high = h
                    continue

                # -------- After T1: BE SL + candle TSL + T2 --------
                if direction == "LONG":
                    t2_price = entry_price + t2_points

                    # Hit T2?
                    if h >= t2_price:
                        exit_price = t2_price
                        realized_pnl += size_remain * (
                            exit_price - entry_price
                        )
                        trades.append(
                            {
                                "instrument": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "T2",
                                "pnl": realized_pnl,
                            }
                        )
                        in_trade = False
                        break

                    # Candle TSL (close below previous low)
                    if prev_low is not None and c < prev_low:
                        exit_price = c
                        realized_pnl += size_remain * (
                            exit_price - entry_price
                        )
                        trades.append(
                            {
                                "instrument": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "TSL_PREV_LOW",
                                "pnl": realized_pnl,
                            }
                        )
                        in_trade = False
                        break

                    # BE SL (intrabar)
                    if l <= be_sl:
                        exit_price = be_sl
                        realized_pnl += size_remain * (
                            exit_price - entry_price
                        )
                        trades.append(
                            {
                                "instrument": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "SL_BE",
                                "pnl": realized_pnl,
                            }
                        )
                        in_trade = False
                        break

                else: # SHORT
                    t2_price = entry_price - t2_points

                    # Hit T2?
                    if l <= t2_price:
                        exit_price = t2_price
                        realized_pnl += size_remain * (
                            entry_price - exit_price
                        )
                        trades.append(
                            {
                                "instrument": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "T2",
                                "pnl": realized_pnl,
                            }
                        )
                        in_trade = False
                        break

                    # Candle TSL (close above previous high)
                    if prev_high is not None and c > prev_high:
                        exit_price = c
                        realized_pnl += size_remain * (
                            entry_price - exit_price
                        )
                        trades.append(
                            {
                                "instrument": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "TSL_PREV_HIGH",
                                "pnl": realized_pnl,
                            }
                        )
                        in_trade = False
                        break

                    # BE SL
                    if h >= be_sl:
                        exit_price = be_sl
                        realized_pnl += size_remain * (
                            entry_price - exit_price
                        )
                        trades.append(
                            {
                                "instrument": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "SL_BE",
                                "pnl": realized_pnl,
                            }
                        )
                        in_trade = False
                        break

                prev_low = l
                prev_high = h
                continue

            # ------------- No trade open: look for first breakout -------------
            if any(tr["date"] == day and tr["instrument"] == label for tr in trades):
                break

            if not in_trade:
                # Long breakout
                if c > or_high:
                    in_trade = True
                    direction = "LONG"
                    entry_price = c
                    entry_time = ts
                    size_remain = 1.0
                    realized_pnl = 0.0
                    reached_t1 = False
                    prev_low = l
                    prev_high = h
                    continue

                # Short breakout
                if c < or_low:
                    in_trade = True
                    direction = "SHORT"
                    entry_price = c
                    entry_time = ts
                    size_remain = 1.0
                    realized_pnl = 0.0
                    reached_t1 = False
                    prev_low = l
                    prev_high = h
                    continue

            prev_low = l
            prev_high = h

        # Safety: if day ends & still in trade w/o EOD_EXIT candle
        if in_trade:
            last_row = after_orb_df.iloc[-1]
            exit_price = last_row["close"]
            realized_pnl += (
                size_remain * (exit_price - entry_price)
                if direction == "LONG"
                else size_remain * (entry_price - exit_price)
            )
            trades.append(
                {
                    "instrument": label,
                    "date": day,
                    "direction": direction,
                    "entry_time": entry_time,
                    "entry_price": entry_price,
                    "exit_time": last_row["timestamp"],
                    "exit_price": exit_price,
                    "reason": "DAY_END_FALLBACK",
                    "pnl": realized_pnl,
                }
            )

    return trades


def summarize(trades, label):
    if not trades:
        print(f"No trades generated for {label}.")
        return

    pnl_list = [t["pnl"] for t in trades]

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
    print(f"Win rate : {wins / total_trades * 100:.2f}%")
    print(f"Total PnL : {sum(pnl_list):.2f} (index points)")
    print(f"Avg / trade : {sum(pnl_list) / total_trades:.2f}")


if __name__ == "__main__":
    all_trades = []
    for label, cfg in INSTRUMENTS.items():
        df = load_data(cfg["csv"])
        trades = backtest_orb(df, cfg["t1"], cfg["t2"], label)
        summarize(trades, label)
        all_trades.extend(trades)
