# Monthly-consistency research

Offline research only. Nothing here registers a production strategy, calls an order
endpoint, changes the bot, or activates a Lab candidate. The strategy emits existing
long/exit/stop intents; a research adapter reuses the shared Decimal replay, sizing,
exchange filters, funding and monthly breaker. No new dependencies.

## Responsibilities

- `regime_long.py`: pure causal indicators and long/flat decisions, validated parameters.
- `replay.py`: experimental intent dispatch and reconciled monthly account metrics.
- `study.py`: the dated September 2026 study protocol, bounded search, retrospective
  validation, cost/capital sensitivity and immutable evidence. This is a fixed study,
  not a general automatic promotion or live strategy-design service.

## Reproduce this study

Run from the repository root using the existing Lab environment and verified public
Binance artifacts. These are actual candles/funding, **not raw-trade execution data**.

```sh
experiments/experiment_lab/.venv/bin/python -m experiment_lab.research.study \
  --dataset .lab-data/qa/artifacts/7d806927e478194e1fd2962933775b5bf3d26e5612c2ae4d03c784c1cd23af20.json \
  --recent .lab-data/comparisons/2026-09-06-three-months-200/artifacts/18546f7031043032a70700d27b70c7bb18aacb47e525f2e3ec466e358edbd8df.json \
  --output .lab-data/monthly-consistency/2026-09-06/artifacts
```

Structured progress goes to stdout. Each result contains parameters, effective account
configuration, fees/slippage, funding, trades, equity and accounting reconciliation.
Artifacts use SHA-256 identity and atomic persistence. The final event identifies the
report; its selection artifact links every trial, including failures of the research
objective. No provider credentials or LLM calls are needed for this deterministic grid.

The first 24 candidates use only September 2023–August 2025. The second round changes
one parameter at a time around that leader (six breakout or eight pullback neighbors).
The winner is locked before later-year, full-period and recent-period evaluations.
Historical reuse means this is **not an untouched holdout**. All full calendar months
count in the denominator, including flat months. Partial months are identified.

The selected hypothesis did not achieve the requested >60% profitable months. See
`docs/qa/reports/MONTHLY_CONSISTENCY_RESEARCH_2026_09_06.md` for findings and limitations.
Do not export/register it as live-ready. Future promotion needs a proper strategy
manifest, production-adapter parity, tick/order-lifecycle verification, independent
forward evidence and explicit operator approval. Research parameters are not live
configuration. The validated v6 plugin and stop-free short sleeve remain unchanged.
