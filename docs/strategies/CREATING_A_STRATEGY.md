# Creating a compatible strategy

CryptoPilot uses a versioned, fail-closed strategy plugin contract. Adding a
validated strategy should require a new plugin, tests, and evidence—not edits to
the scheduler, bot, market API, risk policy wiring, settings UI, or trade filter.

For parameter-only releases, reuse a pure shared strategy implementation and pin
the constructor parameters. Give the variant its own ID/release, no inherited
legacy aliases and `packaged_default=False`. Do not mutate the original registered
instance. `trend_rider_refined_v1_4h.py` is an example. Shared decision code lives in
`packages/strategy_runtime`; the backend module only registers the release.

Replay and live execution must use the same exchange-filter policy for quantity
and protective-price rounding. The refined-release QA harness checks every public
closed-candle decision against the prepared replay path and compares complete
equity/trade histories. Its dataset hashes and source hashes are retained alongside
the result. This checks software equivalence under fixed inputs, not identical
exchange fills or forward profitability.

## Naming

The module filename and `manifest.strategy_id` must be identical and include the
decision timeframe:

```text
<strategy_name>_v<release>_<timeframe>.py
trend_rider_v6_4h.py
```

Use lowercase letters, numbers, and underscores. The final suffix must match
`manifest.market.interval`. The owner-facing `display_name` follows
[NAMING.md](NAMING.md), for example `Atlas 6 Trail · 4h`. Machine IDs remain stable
when product labels change.

## Add a plugin

1. Copy `docs/strategies/templates/strategy_template.py` to
   `backend/app/strategies/plugins/<final-valid-name>.py`.
2. Keep one public `PLUGIN = register(...)` export.
3. Complete the immutable manifest. It owns the symbol, interval, closed-candle
   decision point, warm-up/history window, capabilities, risk policy, education,
   and checked-in validation reference.
4. Implement `on_candle(candles, state)` as a pure deterministic function. It may
   emit intents only. It must not read clocks, environment variables, databases,
   networks, files, credentials, account APIs, or place/size orders.
5. Implement `inspect(candles)` as a pure, read-only projection of this strategy's
   owner-facing conditions, or return `None` until warm-up is complete. The generic
   Overview must never contain strategy-specific indicator or rule logic.
6. Never use an in-progress candle. Signals are decided after a bar closes and
   normal entries execute at the next bar open.
7. Add unit tests for warm-up, entries, exits, management, inspection, determinism, and all
   declared capabilities.
8. Add chronological replay tests using the production plugin and production
   risk/filter code. Replay bars in timestamp order, preserve prior state, decide
   on each closed bar, execute at the next open, and model intrabar stop/TP order,
   fees, funding, exchange rounding, breakers, and skipped orders.
9. Store a reproducible report under `docs/qa/reports/` and set validation status
   to `verified` only after every gate passes.

## Required gates

From the repository root:

```bash
cd backend
.venv/bin/python -m app.strategies validate
.venv/bin/python -m pytest
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
.venv/bin/mypy app
```

Then run the frontend lint, typecheck, tests, and build, plus the isolated
backtesting lab. A new interval is an architecture/policy change: discovery
rejects intervals other than the currently approved closed `4h` feed until that
change is reviewed and the generic scheduler is proven for it.

## Activation safety

The UI exposes only registered manifest information and default selection; it
does not edit strategy parameters. Switching is audit logged and allowed only
while the bot is stopped and the application has no open trade. On start, Binance
is reconciled before evaluation. Production means the real execution code path
in DEMO until the separately controlled LIVE approval gates are satisfied.
