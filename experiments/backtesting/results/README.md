# Generated results

Each run creates `results/runs/<UTC timestamp>/` containing:

- `summary.json` — headline metrics and assumptions
- `manifest.json` — input hashes and reproducibility metadata
- `equity.csv` — closed-candle equity curve
- `trades.csv` — round trips and realized outcomes
- `monthly.csv` — calendar-month returns
- `report.md` — human-readable result

`results/runs/` is ignored because the inputs and outputs are reproducible and
time-stamped. Copy a run into a reviewed report under `docs/` only after its
assumptions and validation gates are accepted.
