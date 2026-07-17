# Backend Development Guidelines (Python 3.11 · FastAPI)

## Layout & style

- Package layout is fixed by `ARCHITECTURE.md` — new code goes in the module that owns
  the concern; if no module owns it, that's a design discussion, not a new util file.
- **Typed everywhere**: `mypy --strict` clean. Public functions have full annotations;
  `Any` needs a comment justifying it.
- Lint/format: `ruff` (lint + format). Line length 100. Naming: `snake_case` functions,
  `PascalCase` classes, `UPPER_CASE` constants; module names are nouns.
- Async-first: FastAPI handlers and the bot loop are `async`; blocking I/O (pg_dump,
  file ops) goes through `asyncio.to_thread`. Never block the event loop — a stalled
  loop misses candle closes.

## Domain rules

- **`Decimal` for money** — constructed from `str`, never from `float`. Quantization
  happens once, at the exchange-filter step (`execution/filters.py`), with explicit
  rounding mode `ROUND_DOWN` for quantities.
- **Datetimes:** `datetime.now(timezone.utc)`; naive datetimes are forbidden (lint).
- **Strategies are pure:** `on_candle(candles, state) -> list[Intent]` — no I/O, no
  clock reads, no randomness. All context arrives as arguments. This is what makes
  parity testing and determinism possible.
- **Errors:** never swallow. Domain exceptions (`ExchangeError`, `ReconcileMismatch`,
  `InsufficientMargin`) carry structured context; the bot loop's top-level handler maps
  them to events + safe-mode/pause decisions. `except Exception` exists only at loop
  boundaries and always logs + events.
- **Events are the spine:** any state change an operator could care about writes an
  `events` row with a reconstructable `payload_json`. When in doubt, event it.

## FastAPI specifics

- Routers thin, services fat: routers validate (Pydantic v2 models), call a service,
  shape the response. No business logic in routers, no SQLAlchemy in routers.
- Response models are explicit (`response_model=`); secrets have no response fields at
  all (write-only by construction).
- Dependency-inject sessions and current-user; no module-level DB sessions.
- WebSocket push: one connection manager; messages are typed dicts
  (`{"type": "position", ...}`); client re-syncs on reconnect via REST, not replay.

## Data access

- SQLAlchemy 2.0 style, explicit `select()`; no lazy relationship loading in the bot
  loop. Transactions are explicit and short; the bot never holds a transaction across
  an exchange call.
- Migrations: Alembic autogenerate then **hand-review the diff** — autogenerate lies
  about server defaults and constraint names.

## Testing hooks

Design for testability: `BinanceClient` behind an interface with a recorded/mock
implementation; clock injected (`TimeProvider`) so 4h boundaries and month rollovers
are testable; notifier and LLM behind interfaces. See `TESTING_GUIDELINES.md`.
