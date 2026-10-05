# Atlas execution reference

`backend/tests/fixtures/atlas7_1h_2026.csv` is public BTCUSDT market/funding input.
`atlas7_execution_oracle.json` contains reference hashes, parameters and configuration
only. Equity, exposure, trades and research findings are not published as fixtures.

The backend integration test runs `run_atlas_oracle.py` in an isolated subprocess.
It loads unchanged MIR source and replaces only numba's compilation decorator with
an identity decorator, so the original expressions run as plain Python using the
backend's existing numpy/pandas dependencies. Production code is not used to build
expected results. The reference output is returned in memory and Decimal assertions
compare every hourly equity observation and reduction event.

`build_atlas_oracle.py` rebuilds market input and hash/config metadata from locally
available MIR input datasets. It requires a QA environment with numba, numpy and
pandas. It never publishes financial result arrays. Frozen `research/` and the MIR
engine/strategy source must remain unchanged.

Run the regression from `backend/`:

```sh
.venv/bin/python -m pytest -q tests/integration/test_atlas_hourly_oracle.py
```
