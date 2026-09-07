# Reproduce the September 2026 timeframe study

This is an offline extension, not a live strategy registration. See the full findings
in `docs/qa/reports/TIMEFRAME_PROFIT_RESEARCH_2026_09_06.md`.

From repository root:

```sh
experiments/experiment_lab/.venv/bin/python -m experiment_lab.research.timeframe_study \
  --dataset .lab-data/timeframe-research/2026-09-06/artifacts/aaf61948947def17f230c88e785472281a0dce8fee4c055018b2b750d372f661.json \
  --dataset .lab-data/timeframe-research/2026-09-06/artifacts/8d0d320192b2bb7e59a1a5c18e843ce155b547b411aeebe4f34db9ec6a4d0234.json \
  --dataset .lab-data/timeframe-research/2026-09-06/artifacts/b647dc3d1af717e21943b9a9cbbc00dbb76ffbac26a109d89d054d8177b1ec13.json \
  --output .lab-data/timeframe-research/2026-09-06/artifacts

experiments/experiment_lab/.venv/bin/python -m experiment_lab.research.profit_refinement \
  --dataset .lab-data/timeframe-research/2026-09-06/artifacts/b647dc3d1af717e21943b9a9cbbc00dbb76ffbac26a109d89d054d8177b1ec13.json \
  --output .lab-data/timeframe-research/2026-09-06/artifacts
```

Both commands log structured progress and finish with a content-addressed report ID.
They use the fixed September 2023–August 2026 snapshot; they do not download future
periods or automatically renew an optimization campaign. New code hashes produce new
evidence; never relabel old artifacts as having run under a new evaluator.

The reconciled datasets preserve native downloads and refer to two actual Binance
1-minute source archives. `reconcile_candles.reconcile` regenerates them from their
original dataset and those sources. The cross-timeframe aggregation gate must pass
before any candidate runs. Raw trades, order-book liquidity and liquidation remain
unmodeled. Higher-timeframe information is available only after its candle closes.

The existing validated v6 contract remains unchanged. A future multi-timeframe live
plugin needs an approved data contract and adapter parity before registration; this
research-only prepared-frame adapter must not be dropped into the live plugin registry.
