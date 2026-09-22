"""JEV (TypeSafe System One) regime judgments on anonymised 4h market states.

Design rules, following TypeSafe's guidance for jev-1.13:
* All arithmetic stays in code; JEV receives named buckets plus rounded context.
* The state never contains dates, absolute prices, or the asset's name, so the model
  cannot recall what happened next from its pre-training (look-ahead leakage).
* Each question is atomic; code combines the answers.
* Every answer is cached on disk keyed by the exact request, so backtests replay the
  same judgments deterministically without new API calls.
The API key is read from the TYPESAFE_API_KEY environment variable only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mir import indicators as ind
from mir.data import Market

CACHE = Path(__file__).resolve().parents[2] / "results" / "cache" / "jev_answers.jsonl"
QUESTIONS_VERSION = "q1"
MODEL = "jev-1.13.0"  # pin the version so cached thresholds stay meaningful

QUESTIONS: dict[str, dict] = {
    "phase": {
        "type": "choice",
        "instructions": "Which description best matches the recent price behaviour in the state?",
        "criteria": {
            "uptrend": "Price is advancing: mostly higher highs and higher lows, holding above "
                       "a rising long-term average.",
            "downtrend": "Price is declining: mostly lower highs and lower lows, holding below "
                         "a falling long-term average.",
            "sideways": "Price is moving sideways without a clear direction, crossing its "
                        "averages back and forth.",
        },
    },
    "chop": {
        "type": "noul",
        "instructions": "The market in the state is choppy: price keeps reversing, so a new "
                        "trend-following trade would likely be stopped out.",
    },
    "strength": {
        "type": "score",
        "instructions": "How strong is the current trend in the state, in either direction?",
        "criteria": ["No trend", "Weak trend", "Moderate trend", "Strong trend"],
    },
    "overextended": {
        "type": "noul",
        "instructions": "The latest move in the state is overextended, so a pullback against "
                        "it is likely soon.",
    },
    "squeeze": {
        "type": "noul",
        "instructions": "Volatility in the state is unusually compressed, so a large breakout "
                        "move is likely to start soon.",
    },
    "up_next": {
        "type": "noul",
        "instructions": "Based on the state, the price is more likely to be higher than lower "
                        "three days from now.",
    },
}


def _bucket(x: float, edges: list[float], names: list[str]) -> str:
    for edge, name in zip(edges, names):
        if x < edge:
            return name
    return names[-1]


def _pct(x: float) -> str:
    return f"{x * 100:+.0f}%"


def build_states(market: Market) -> pd.DataFrame:
    """One anonymised description per closed 4h candle (causal)."""
    df = market.h4
    c = df["close"]
    sma200 = ind.sma(c, 200)
    ema50, ema200 = ind.ema(c, 50), ind.ema(c, 200)
    atrp = ind.atr(df, 14) / c
    atr_rank = atrp.rolling(360, min_periods=360).rank(pct=True)
    er42 = ind.efficiency_ratio(c, 42)
    hi30 = df["high"].rolling(180).max()
    lo30 = df["low"].rolling(180).min()
    hi90 = df["high"].rolling(540).max()
    cross = np.sign(c - ema50).diff().abs().gt(0).astype(int).rolling(60).sum()
    upc = (df["close"] > df["open"]).astype(int).rolling(6).sum()
    vol7 = df["volume"].rolling(42).mean()
    vol30 = df["volume"].rolling(180).mean()
    fund_events = pd.Series(market.funding_h1, index=market.h1.index)
    fund_events = fund_events[fund_events != 0]
    fund_avg = fund_events.rolling(3).mean().reindex(market.h1.index, method="ffill")
    # funding known at the 4h close = value at the decision (last 1h) bar
    fund4 = pd.Series(fund_avg.to_numpy()[market.dec_idx_h1], index=df.index)

    rows = []
    for k in range(len(df)):
        if k < 540 or not np.isfinite(atr_rank.iloc[k]):
            rows.append(None)
            continue
        ck = c.iloc[k]
        d_sma = ck / sma200.iloc[k] - 1
        slope = sma200.iloc[k] / sma200.iloc[k - 30] - 1
        gap = ema50.iloc[k] / ema200.iloc[k] - 1
        r1 = ck / c.iloc[k - 6] - 1
        r7 = ck / c.iloc[k - 42] - 1
        r30 = ck / c.iloc[k - 180] - 1
        pos = (ck - lo30.iloc[k]) / max(hi30.iloc[k] - lo30.iloc[k], 1e-9)
        dd90 = ck / hi90.iloc[k] - 1
        fr = fund4.iloc[k]
        vr = vol7.iloc[k] / vol30.iloc[k]
        state = {
            "market": "a large, liquid cryptocurrency perpetual futures contract, "
                      "observed on closed 4-hour candles",
            "price_vs_long_term_average_33_days": _bucket(
                d_sma, [-0.15, -0.05, -0.01, 0.01, 0.05, 0.15],
                ["far below", "below", "slightly below", "at", "slightly above", "above",
                 "far above"]) + f" ({_pct(d_sma)})",
            "long_term_average_direction_last_5_days": _bucket(
                slope, [-0.03, -0.01, 0.01, 0.03],
                ["falling steeply", "falling", "flat", "rising", "rising steeply"]),
            "medium_average_vs_long_average": ("above" if gap > 0 else "below")
            + f" by {abs(gap) * 100:.1f}%",
            "change_last_1_day": _bucket(
                r1, [-0.04, -0.015, -0.005, 0.005, 0.015, 0.04],
                ["sharply down", "down", "slightly down", "flat", "slightly up", "up",
                 "sharply up"]) + f" ({_pct(r1)})",
            "change_last_7_days": _bucket(
                r7, [-0.12, -0.06, -0.02, 0.02, 0.06, 0.12],
                ["sharply down", "down", "slightly down", "flat", "slightly up", "up",
                 "sharply up"]) + f" ({_pct(r7)})",
            "change_last_30_days": _bucket(
                r30, [-0.25, -0.12, -0.05, 0.05, 0.12, 0.25],
                ["sharply down", "down", "slightly down", "flat", "slightly up", "up",
                 "sharply up"]) + f" ({_pct(r30)})",
            "position_in_30_day_range": _bucket(
                pos, [0.1, 0.35, 0.65, 0.9],
                ["at the bottom", "in the lower part", "in the middle", "in the upper part",
                 "at the top"]),
            "distance_from_90_day_high": f"{abs(dd90) * 100:.0f}% below the 90-day high"
            if dd90 < -0.005 else "at the 90-day high",
            "volatility_vs_last_60_days": _bucket(
                atr_rank.iloc[k], [0.1, 0.35, 0.65, 0.9],
                ["very low (compressed)", "low", "normal", "high", "very high"]),
            "path_efficiency_last_7_days": _bucket(
                er42.iloc[k], [0.1, 0.2, 0.35, 0.5],
                ["very choppy", "choppy", "mixed", "directional", "strongly directional"]),
            "crosses_of_medium_average_last_10_days": _bucket(
                cross.iloc[k], [1, 3, 6], ["none", "few", "several", "many"]),
            "last_6_candles": f"{int(upc.iloc[k])} of the last 6 candles closed higher",
            "funding": _bucket(
                fr, [-0.00005, 0.00005, 0.0003],
                ["shorts pay longs", "neutral", "longs pay a normal premium",
                 "longs pay a high premium"]),
            "volume_last_7_days_vs_30_days": _bucket(
                vr, [0.7, 0.9, 1.1, 1.4], ["much lower", "lower", "similar", "higher",
                                           "much higher"]),
        }
        rows.append(state)
    return pd.DataFrame({"state": rows}, index=df.index)


def request_key(state: dict) -> str:
    blob = json.dumps({"s": state, "q": QUESTIONS_VERSION, "m": MODEL}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def load_cache() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if CACHE.exists():
        with CACHE.open() as handle:
            for line in handle:
                row = json.loads(line)
                out[row["key"]] = row
    return out


async def _ask_all(states: list[dict], concurrency: int = 12) -> None:
    from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cached = load_cache()
    todo = {}
    for s in states:
        key = request_key(s)
        if key not in cached:
            todo[key] = s
    print(f"JEV: {len(states)} states, {len(todo)} uncached unique requests")
    if not todo:
        return
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    done = 0
    tokens = 0
    t0 = time.time()
    async with AsyncTypeSafeClient(model=MODEL, retry=RetryPolicy(max_retries=6)) as client:
        with CACHE.open("a") as handle:

            async def one(key: str, state: dict) -> None:
                nonlocal done, tokens
                async with sem:
                    res = await client.system_one(state=state, questions=QUESTIONS)
                ans = json.loads(res.model_dump_json())
                async with lock:
                    handle.write(json.dumps({"key": key, "model": ans.get("model"),
                                             "answers": ans["answers"],
                                             "usage": ans.get("usage")}) + "\n")
                    done += 1
                    tokens += int((ans.get("usage") or {}).get("input_tokens", 0))
                    if done % 500 == 0:
                        handle.flush()
                        rate = done / (time.time() - t0)
                        print(f"  {done}/{len(todo)}  {rate:.1f}/s  input tokens {tokens:,}")

            await asyncio.gather(*(one(k, s) for k, s in todo.items()))
    print(f"JEV: finished {done} requests, {tokens:,} input tokens, "
          f"~${tokens / 1e6 * 0.042:.3f} at $0.042/Mtok")


def ask_all(states: list[dict], concurrency: int = 12) -> None:
    asyncio.run(_ask_all(states, concurrency))


def answers_frame(market: Market, states: pd.DataFrame | None = None) -> pd.DataFrame:
    """Flatten cached answers per 4h bar (NaN where no state / no answer)."""
    states = build_states(market) if states is None else states
    cache = load_cache()
    recs = []
    for s in states["state"]:
        if s is None:
            recs.append({})
            continue
        row = cache.get(request_key(s))
        if row is None:
            recs.append({})
            continue
        a = row["answers"]
        ph = a["phase"]["probabilities"]
        recs.append({
            "p_up": ph.get("uptrend", np.nan), "p_down": ph.get("downtrend", np.nan),
            "p_side": ph.get("sideways", np.nan), "phase_conf": a["phase"]["confidence"],
            "phase": a["phase"]["choice"], "chop": a["chop"]["noul"],
            "strength": a["strength"]["score"], "overextended": a["overextended"]["noul"],
            "squeeze": a["squeeze"]["noul"], "up_next": a["up_next"]["noul"],
        })
    return pd.DataFrame(recs, index=states.index)
