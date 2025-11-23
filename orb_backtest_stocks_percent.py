import pandas as pd
from datetime import time

STOCKS = {
    "SBIN": {
        "csv": "SBIN_5min_SmartAPI.csv",
        "sl_pct": 0.005, # 0.50%
        "t1_pct": 0.006, # 0.60%
        "t2_pct": 0.012, # 1.20%
    },
    "ICICIBANK": {
        "csv": "ICICIBANK_5min_SmartAPI.csv",
        "sl_pct": 0.004, # 0.40%
        "t1_pct": 0.006, # 0.60%
        "t2_pct": 0.012, # 1.20%
    },
}

MARKET_START = time(9, 15)
ORB_END = time(9, 30) # 15-min opening range
EOD_EXIT = time(15, 15)


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def backtest_stock_orb(df: pd.DataFrame, sl_pct: float, t1_pct: float, t2_pct: float, label: str):
    trades = []
    df = df.copy()
    df["date"] = df["timestamp"].dt.date

    for day, day_df in df.groupby("date"):
        day_df = day_df.sort_values("timestamp").reset_index(drop=True)

        # Keep normal market hours only
        day_df = day_df[
            (day_df["timestamp"].dt.time >= MARKET_START)
            & (day_df["timestamp"].dt.time <= EOD_EXIT)
        ]
        if day_df.empty:
            continue

        # ---- Build Opening Range 9:15–9:30 ----
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
        be_sl = None # break-even SL after T1

        after_orb_df = day_df[day_df["timestamp"].dt.time > ORB_END]
        if after_orb_df.empty:
            continue

        for _, row in after_orb_df.iterrows():
            ts = row["timestamp"]
            t = ts.time()
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]

            # ---------- Manage open trade ----------
            if in_trade:
                # Time-based exit
                if t >= EOD_EXIT:
                    exit_price = c
                    realized_pnl += (
                        size_remain * (exit_price - entry_price)
                        if direction == "LONG"
                        else size_remain * (entry_price - exit_price)
                    )
                    trades.append({
                        "stock": label,
                        "date": day,
                        "direction": direction,
                        "entry_time": entry_time,
                        "entry_price": entry_price,
                        "exit_time": ts,
                        "exit_price": exit_price,
                        "reason": "EOD",
                        "pnl": realized_pnl,
                    })
                    in_trade = False
                    break

                if not reached_t1:
                    # BEFORE T1: use % SL + check T1/T2
                    sl_long = entry_price * (1 - sl_pct)
                    sl_short = entry_price * (1 + sl_pct)

                    if direction == "LONG":
                        # SL hit?
                        if l <= sl_long:
                            exit_price = sl_long
                            realized_pnl += size_remain * (exit_price - entry_price)
                            trades.append({
                                "stock": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "SL_BEFORE_T1",
                                "pnl": realized_pnl,
                            })
                            in_trade = False
                            break

                        t1_price = entry_price * (1 + t1_pct)
                        t2_price = entry_price * (1 + t2_pct)

                        # T2 first (could include T1 same bar)
                        if h >= t2_price:
                            # assume 50% at T1, 50% at T2 in same bar
                            realized_pnl += 0.5 * (t1_price - entry_price)
                            realized_pnl += 0.5 * (t2_price - entry_price)
                            trades.append({
                                "stock": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": t2_price,
                                "reason": "T1+T2_SAME_BAR",
                                "pnl": realized_pnl,
                            })
                            in_trade = False
                            break

                        # Only T1 hit
                        if h >= t1_price:
                            realized_pnl += 0.5 * (t1_price - entry_price)
                            size_remain = 0.5
                            reached_t1 = True
                            be_sl = entry_price # break-even SL
                        else:
                            prev_low = l
                            prev_high = h
                            continue

                    else: # SHORT
                        if h >= sl_short:
                            exit_price = sl_short
                            realized_pnl += size_remain * (entry_price - exit_price)
                            trades.append({
                                "stock": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": exit_price,
                                "reason": "SL_BEFORE_T1",
                                "pnl": realized_pnl,
                            })
                            in_trade = False
                            break

                        t1_price = entry_price * (1 - t1_pct)
                        t2_price = entry_price * (1 - t2_pct)

                        if l <= t2_price:
                            realized_pnl += 0.5 * (entry_price - t1_price)
                            realized_pnl += 0.5 * (entry_price - t2_price)
                            trades.append({
                                "stock": label,
                                "date": day,
                                "direction": direction,
                                "entry_time": entry_time,
                                "entry_price": entry_price,
                                "exit_time": ts,
                                "exit_price": t2_price,
                                "reason": "T1+T2_SAME_BAR",
                                "pnl": realized_pnl,
                            })
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

                    prev_low = l
                    prev_high = h
                    continue

                # -------- AFTER T1: BE SL + candle TSL + T2 --------
                t2_price_long = entry_price * (1 + t2_pct)
                t2_price_short = entry_price * (1 - t2_pct)

                if direction == "LONG":
                    # T2?
                    if h >= t2_price_long:
                        exit_price = t2_price_long
                        realized_pnl += size_remain * (exit_price - entry_price)
                        trades.append({
                            "stock": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "T2",
                            "pnl": realized_pnl,
                        })
                        in_trade = False
                        break

                    # Candle TSL (close < prev low)
                    if prev_low is not None and c < prev_low:
                        exit_price = c
                        realized_pnl += size_remain * (exit_price - entry_price)
                        trades.append({
                            "stock": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "TSL_PREV_LOW",
                            "pnl": realized_pnl,
                        })
                        in_trade = False
                        break

                    # Break-even SL
                    if be_sl is not None and l <= be_sl:
                        exit_price = be_sl
                        realized_pnl += size_remain * (exit_price - entry_price)
                        trades.append({
                            "stock": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "SL_BE",
                            "pnl": realized_pnl,
                        })
                        in_trade = False
                        break

                else: # SHORT
                    if l <= t2_price_short:
                        exit_price = t2_price_short
                        realized_pnl += size_remain * (entry_price - exit_price)
                        trades.append({
                            "stock": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "T2",
                            "pnl": realized_pnl,
                        })
                        in_trade = False
                        break

                    if prev_high is not None and c > prev_high:
                        exit_price = c
                        realized_pnl += size_remain * (entry_price - exit_price)
                        trades.append({
                            "stock": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "TSL_PREV_HIGH",
                            "pnl": realized_pnl,
                        })
                        in_trade = False
                        break

                    if be_sl is not None and h >= be_sl:
                        exit_price = be_sl
                        realized_pnl += size_remain * (entry_price - exit_price)
                        trades.append({
                            "stock": label,
                            "date": day,
                            "direction": direction,
                            "entry_time": entry_time,
                            "entry_price": entry_price,
                            "exit_time": ts,
                            "exit_price": exit_price,
                            "reason": "SL_BE",
                            "pnl": realized_pnl,
                        })
                        in_trade = False
                        break

                prev_low = l
                prev_high = h
                continue

            # ---------- No open trade: look for first breakout ----------
            if any(tr["date"] == day and tr["stock"] == label for tr in trades):
                break

            # Long breakout
            if c > or_high and not in_trade:
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
            if c < or_low and not in_trade:
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

        # Safety: if still in trade after last bar
        if in_trade:
            last_row = after_orb_df.iloc[-1]
            exit_price = last_row["close"]
            realized_pnl += (
                size_remain * (exit_price - entry_price)
                if direction == "LONG"
                else size_remain * (entry_price - exit_price)
            )
            trades.append({
                "stock": label,
                "date": day,
                "direction": direction,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "exit_time": last_row["timestamp"],
                "exit_price": exit_price,
                "reason": "DAY_END_FALLBACK",
                "pnl": realized_pnl,
            })

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
    if total_trades > 0:
        print(f"Win rate : {wins / total_trades * 100:.2f}%")
        print(f"Total PnL : {sum(pnl_list):.2f} (stock price points)")
        print(f"Avg / trade : {sum(pnl_list) / total_trades:.2f}")


if __name__ == "__main__":
    for label, cfg in STOCKS.items():
        df = load_data(cfg["csv"])
        trades = backtest_stock_orb(df, cfg["sl_pct"], cfg["t1_pct"], cfg["t2_pct"], label)
        summarize(trades, label)
