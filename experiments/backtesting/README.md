# CryptoPilot backtesting lab

This folder is the reusable, isolated experiment workspace for Trend Rider v6.
It does **not** modify the frozen `research/` tree and it never connects to an
account or places an order.

## What it proves

The lab has three separate evidence layers:

1. `pytest backend/tests/parity` proves the production composite engine still
   matches the frozen research engine bar-for-bar on the validated dataset.
2. `trend_rider_lab.cli run` replays the production strategy plugin
   chronologically over public Binance BTCUSDT USD-M 4h candles. It calls
   `on_candle()` for every closed bar and uses production Decimal sizing/filter
   functions. The independent reference engine exists only as a comparison oracle.
3. `trend_rider_lab.cli audit-live-path` checks whether the live bot handles the
   intent and breaker vocabulary, persisted trade state, fill synchronization,
   order replacement, safe-mode position management, and next-open execution
   required to reproduce the validated strategy. A profitable replay is not
   evidence of deployable parity when this audit reports gaps.

## Folder structure

```text
experiments/backtesting/
├── data/raw/                 downloaded public candles, funding, filters
├── results/runs/<timestamp>/ reproducible CSV/JSON/Markdown output
├── src/trend_rider_lab/      downloader, replay engine, metrics, CLI
└── tests/                    deterministic lab tests
```

Raw data and timestamped results are intentionally ignored by Git. Each run writes
SHA-256 hashes and its complete assumptions to `manifest.json`.

## Run

From the repository root:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m trend_rider_lab.cli run \
  --years 3 \
  --initial-capital 100
```

Re-run without downloading:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m trend_rider_lab.cli run \
  --years 3 \
  --initial-capital 100 \
  --reuse-data
```

Run the same replay with both independent monthly breakers disabled:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m trend_rider_lab.cli run \
  --years 5 \
  --initial-capital 200 \
  --reuse-data \
  --no-monthly-breakers
```

Run a venue-filter control using the read-only DEMO filter snapshot:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m trend_rider_lab.cli run \
  --years 3 \
  --initial-capital 100 \
  --reuse-data \
  --filters-path experiments/backtesting/data/raw/btcusdt_filters_demo.json
```

Validation:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m pytest -q experiments/backtesting/tests
(cd backend && .venv/bin/python -m pytest -q tests/parity)
backend/.venv/bin/python -m trend_rider_lab.cli audit-live-path
```

## Isolated 30-minute and 1-hour research

The lab can also search experimental 30-minute long/short signal families without
registering a production strategy:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m trend_rider_lab.cli search-30m \
  --years 3 \
  --broad-count 1500 \
  --refined-count 1500
```

The deterministic search covers EMA trend, time-series momentum, Donchian breakout,
ATR channel, regime-gated mean reversion, and multi-horizon momentum ensembles. It
selects candidates only on the first two years (one train year plus one validation
year), then evaluates the locked winner on the untouched final year. Signals execute
at the next 30-minute open; 0.05% turnover cost and public historical funding apply.

This command is research-only. It does not modify the frozen `research/` tree, register
a plugin, connect to an account, or change the application's approved closed-4h
scheduler policy.

The stricter six-year asymmetric search selects separate long and short sleeves only
on the older three years, then evaluates the locked composite on the latest three
years. Run both the full family set and the trend-only falsification:

```sh
export PYTHONPATH="$PWD/backend:$PWD/experiments/backtesting/src"
backend/.venv/bin/python -m trend_rider_lab.cli search-30m-asymmetric \
  --timeframe 30m \
  --leader-count 12
backend/.venv/bin/python -m trend_rider_lab.cli search-30m-asymmetric \
  --timeframe 30m \
  --leader-count 12 \
  --trend-only \
  --reuse-data
backend/.venv/bin/python -m trend_rider_lab.cli search-30m-asymmetric \
  --timeframe 1h \
  --leader-count 12
backend/.venv/bin/python -m trend_rider_lab.cli search-30m-asymmetric \
  --timeframe 1h \
  --leader-count 12 \
  --trend-only \
  --reuse-data
```

The latest evidence and comparison with Trend Rider v6 is recorded in
`results/LATEST_INTRADAY_RESEARCH.md`.

## Replay assumptions

- Public Binance USD-M BTCUSDT 4h candles; only candles whose close time is
  earlier than Binance server time are included.
- Exactly three calendar years ending at the latest closed 4h candle, plus 200
  pre-period warmup bars. Capital starts flat at the period boundary.
- Signals use production `app.strategies.engine` indicators/constants and act at
  the next candle open.
- Long sizing calls production `app.risk.sizing.size_long` with the active plugin
  manifest's risk percentage and leverage cap. Short sizing calls production
  `size_short`, using the strategy's 75% sleeve and 40% volatility target.
- Current public BTCUSDT exchange filters are applied, including lot rounding
  and minimum notional.
- Long fee: 0.04% per fill. Short transaction cost: 0.05% per fill, matching the
  production parity engine constants. No extra invented spread is added.
- Stops gap through to the candle open when the open is worse than the stop.
  When a candle touches both the initial stop and TP1, the stop is processed
  first, matching the production parity engine.
- TP1 closes 40%, moves the remaining stop to entry, and the runner trails at
  highest high minus 4 ATR. Deep-bear shorts resize only when target drift is
  greater than 20%.
- Actual public historical funding rates are applied to positions carried at a
  funding timestamp. Positive funding charges longs and credits shorts. Some
  older Binance funding rows omit `markPrice`; only for those rows, the
  containing 4h candle open proxies the funding notional.
- Independent 4% monthly long and short breakers flatten at the following
  candle open and halt that sleeve until the next UTC calendar month.
- Final equity is marked to the latest closed candle. An open position is not
  fictitiously closed.

This is a deterministic OHLC replay, not tick-level order-book simulation. It
cannot model latency, partial market fills, liquidation-engine behavior, ADL,
API outages, or slippage beyond the explicit costs above. Historical profit is
not a forecast or guarantee.
