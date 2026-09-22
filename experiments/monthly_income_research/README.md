# Monthly-income strategy research (September 2026)

Research workspace behind `docs/qa/reports/MONTHLY-INCOME-STRATEGY-RESEARCH-2026-09-22.md`.
It never reads account credentials, never places orders and is not imported by the backend.
The frozen `research/` tree is untouched.

## Layout

```text
experiments/monthly_income_research/
├── scripts/download.py        public Binance candles + funding -> data/ (gitignored)
├── src/mir/
│   ├── data.py                1h execution timeline, 4h decision bars, funding alignment
│   ├── indicators.py          causal indicators (closed bars only)
│   ├── engine.py              numba event engine: next-open fills, 1h stops/TPs, fees,
│   │                          funding, lot rounding, per-side monthly breakers
│   ├── strategies.py          strategy families as per-4h-bar signals
│   ├── search.py              grid runner + walk-forward selection on monthly returns
│   ├── portfolio.py           walk-forward sleeve portfolios
│   ├── carry.py               delta-neutral funding carry simulation
│   ├── grid.py                neutral futures grid on 15m bars
│   └── jev.py                 anonymised JEV states, cached TypeSafe calls
├── scripts/                   stage runners, JEV evaluation, final evaluation, baselines
├── tests/                     deterministic engine/signal checks
└── results/                   summaries (runs and the JEV answer cache are gitignored)
```

## Environments

Production baselines use the backend virtualenv (it provides `strategy_runtime`):

```sh
cd experiments/monthly_income_research
../../backend/.venv/bin/python scripts/download.py --symbols BTCUSDT --intervals 15m,1h,4h,1d --spot
../../backend/.venv/bin/python scripts/download.py --symbols ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT --intervals 1h
../../backend/.venv/bin/python scripts/baseline_atlas.py
../../backend/.venv/bin/python scripts/atlas_risk_profiles.py
../../backend/.venv/bin/python scripts/export_atlas_monthly.py
```

The research engine needs `numba` and, for JEV, `typesafe-sdk`. Use a separate virtualenv
outside the repository so the backend lock file is unchanged:

```sh
uv venv --python 3.11 /tmp/mir-venv
uv pip install --python /tmp/mir-venv/bin/python numpy==2.2.2 pandas==2.2.3 numba httpx typesafe-sdk pytest
/tmp/mir-venv/bin/python -m pytest -q tests
/tmp/mir-venv/bin/python scripts/grid_stage1.py
/tmp/mir-venv/bin/python scripts/grid_stage2.py
/tmp/mir-venv/bin/python scripts/grid_dual.py
/tmp/mir-venv/bin/python scripts/select_dual.py
/tmp/mir-venv/bin/python scripts/final_eval.py
```

## JEV

`src/mir/jev.py` reads the key only from the `TYPESAFE_API_KEY` environment variable and pins
`jev-1.13.0`. Answers are cached in `results/cache/jev_answers.jsonl` (gitignored), keyed by the
exact state, question version and model, so reruns replay the same judgments without new calls.
A full rebuild is about 14,800 requests and 12M input tokens (about $0.51 at $0.042/Mtok).

```sh
export TYPESAFE_API_KEY=...   # never commit it
/tmp/mir-venv/bin/python scripts/jev_eval.py
```

## Reading the numbers

Monthly returns are marked at each month's last 1h close. "Walk-forward" means each 6-month
test window was chosen using only the 24 months before it. Fixed-configuration results over the
full period are partly in-sample; use the walk-forward figures as the expectation.
