# Strategy plugins

The application discovers every non-underscore Python module in `plugins/`.
Each module owns its identity, market/timeframe, data window, risk policy,
owner-facing explanation, validation evidence, parameters, and deterministic
closed-candle decision code.

The generic application owns Binance I/O, clocks, persistence, reconciliation,
exchange filters, sizing calculations, orders, notifications, and the UI.

Validate the catalog from `backend/`:

```bash
.venv/bin/python -m app.strategies validate
.venv/bin/python -m app.strategies list
```

See `docs/strategies/CREATING_A_STRATEGY.md` before adding a plugin.

`trend_rider_refined_v1_4h` is a separate pinned release implemented in
`strategy_runtime.refined_trend_rider.RefinedTrendRider`. It inherits v6's decision
rules rather than copying them; only the long trail changes to 4.5 ATR. The original
v6 remains the packaged default and keeps its original legacy aliases.

Selection writes the release, symbol, interval and complete parameter snapshot to
the existing audit event. It never starts the bot or switches environment. Extra
parameter fields in selection requests are rejected; changed configurations ship
as new reviewed releases. Settings renders manifest explanations and parameters
generically, including the warning that parity is not proof of profitability.
