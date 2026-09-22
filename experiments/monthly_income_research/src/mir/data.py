"""Load public Binance data and build aligned 1h / 4h views."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data"


@dataclass
class Market:
    """1h execution timeline plus the 4h decision bars derived from it."""

    h1: pd.DataFrame  # index: 1h open time (UTC)
    h4: pd.DataFrame  # index: 4h open time (UTC), aggregated from h1
    funding_h1: np.ndarray  # funding rate applied at each 1h bar open (0 if none)
    dec_idx_h1: np.ndarray  # for each 4h bar k: index of its last 1h bar (decision point)
    month_id_h1: np.ndarray
    spot_h1: pd.DataFrame | None = None

    def to_h1(self, values: np.ndarray, fill: float | bool = np.nan) -> np.ndarray:
        """Place per-4h-bar decision values on the 1h timeline at decision bars."""
        dtype = bool if isinstance(fill, bool) else float
        out = np.full(len(self.h1), fill, dtype=dtype)
        out[self.dec_idx_h1] = values
        return out


def _read(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True)
    frame = frame.set_index("dt").sort_index()
    for col in ("open", "high", "low", "close", "volume", "quote_volume", "taker_buy_base"):
        if col in frame:
            frame[col] = frame[col].astype(float)
    return frame


def load_market(symbol: str = "btcusdt", with_spot: bool = False) -> Market:
    h1 = _read(DATA / f"{symbol}_perp_1h.csv")
    # Start on a 4h boundary so every 4h bar is complete.
    first = h1.index[0]
    start = first.ceil("4h")
    h1 = h1.loc[start:]
    # Drop a trailing partial 4h group (decisions need a closed 4h candle).
    last_full = (len(h1) // 4) * 4
    h1 = h1.iloc[:last_full]
    steps = h1.index.to_series().diff().dropna()
    if not bool((steps == pd.Timedelta("1h")).all()):
        raise ValueError("1h series has gaps")
    groups = np.arange(len(h1)) // 4
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "taker_buy_base": "sum",
    }
    h4 = h1.groupby(groups).agg(agg)
    h4.index = h1.index[::4]
    dec_idx = np.arange(3, len(h1), 4)

    funding = pd.read_csv(DATA / f"{symbol}_funding.csv")
    funding["dt"] = pd.to_datetime(funding["dt"], utc=True, format="mixed")
    bucket = funding.groupby(funding["dt"].dt.floor("1h"))["funding_rate"].sum()
    fund = np.zeros(len(h1))
    pos = h1.index.get_indexer(pd.DatetimeIndex(bucket.index))
    ok = pos >= 0
    fund[pos[ok]] = bucket.to_numpy(dtype=float)[ok]

    month_id = (h1.index.year * 12 + h1.index.month - 1).to_numpy()
    spot = None
    if with_spot:
        spot = _read(DATA / f"{symbol}_spot_1h.csv").reindex(h1.index).ffill()
    return Market(h1=h1, h4=h4, funding_h1=fund, dec_idx_h1=dec_idx, month_id_h1=month_id,
                  spot_h1=spot)
