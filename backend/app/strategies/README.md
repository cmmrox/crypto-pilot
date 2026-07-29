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
