"""Download BTCUSDT klines from data.binance.vision (monthly zips).

Handles the mid-2024 Binance switch of open_time from ms to microseconds
by normalizing per-row. Saves one CSV per interval.
"""
import io
import sys
import zipfile

import pandas as pd
import requests

BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/{iv}/BTCUSDT-{iv}-{ym}.zip"
COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
]


def month_range(start, end):
    cur = pd.Period(start, "M")
    last = pd.Period(end, "M")
    while cur <= last:
        yield str(cur)
        cur += 1


def normalize_ts(v):
    # ms epoch ~1.7e12, us epoch ~1.7e15
    v = int(v)
    if v > 10 ** 14:
        v //= 1000
    return v


def download(interval, start, end, out):
    frames = []
    for ym in month_range(start, end):
        url = BASE.format(iv=interval, ym=ym)
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            print(f"  MISS {interval} {ym} ({r.status_code})", flush=True)
            continue
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            name = z.namelist()[0]
            df = pd.read_csv(z.open(name), header=None, names=COLS)
        # some months ship with a header row
        if isinstance(df.iloc[0]["open_time"], str) and not str(df.iloc[0]["open_time"]).isdigit():
            df = df.iloc[1:]
        df["open_time"] = df["open_time"].map(normalize_ts)
        frames.append(df)
        print(f"  ok {interval} {ym} rows={len(df)}", flush=True)
    full = pd.concat(frames, ignore_index=True)
    for c in ["open", "high", "low", "close", "volume"]:
        full[c] = pd.to_numeric(full[c])
    full["dt"] = pd.to_datetime(full["open_time"], unit="ms", utc=True)
    full = full.sort_values("dt").drop_duplicates("dt").reset_index(drop=True)
    full[["dt", "open", "high", "low", "close", "volume"]].to_csv(out, index=False)
    print(f"SAVED {out} rows={len(full)} span={full['dt'].iloc[0]} .. {full['dt'].iloc[-1]}", flush=True)


if __name__ == "__main__":
    start, end = "2023-06", "2026-06"
    download("4h", start, end, "btc_4h.csv")
    download("15m", start, end, "btc_15m.csv")
    download("1d", start, end, "btc_1d.csv")
    print("DONE", flush=True)
