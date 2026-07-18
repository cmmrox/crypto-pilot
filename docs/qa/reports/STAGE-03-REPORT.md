# Stage 3 — Strategy Engine & Parity Gate — Report

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18. **This is the G1 gate.**

## Scope shipped

Trend Rider v6 (+ v5.2 fallback) as pure strategy plugins, proven **bar-for-bar
identical** to the validated research engine.

- **Plugin framework** (`strategies/base.py`): abstract intents (EnterLong, EnterShort,
  ResizeShort, MoveStop, TakePartial, ExitAll, Halt), `Strategy` protocol, registry.
- **Composite engine** (`strategies/engine.py`): faithful port of the research engine —
  the v5.2 managed long engine + 4% monthly breaker, the deep-bear vol-targeted short
  sleeve (+ turnover costs + 4% sleeve breaker), composed as `r_long + 0.75·r_short`.
- **Plugins** (`trend_rider_v6.py`, `trend_rider_v52.py`): registered, validated params
  pinned, `on_candle` emitting intents; v5.2 is long-only.
- **Strategy library API** (`api/strategies_api.py` + `services/strategies.py`) and the
  Settings strategy-library UI with parity status.
- **Numeric policy:** strategy *decisions* use float64 (identical to the validated
  research engine → exact parity); money/quantities become Decimal at the execution
  boundary (Stage 4). Documented in `strategies/base.py`.

## Parity gate (the headline result)

The parity test (`tests/parity/test_parity.py`) imports the **actual research engine**
(`final_composite.py` + `circuit_breaker.py` + `research_ls.py` + `short_lab.py`), runs
both engines on the full 3-year `btc_4h.csv`, and asserts:

| Check | Result |
|---|---|
| Composite equity, bar-for-bar | ✅ max relative diff **< 1e-9** |
| Long in-market decisions | ✅ max return diff **< 1e-12** |
| Short-exposure decisions | ✅ **0 mismatches** |
| Documented 3-year return reproduced | ✅ **+204.5%** |

CI runs it as a dedicated, mandatory step (`pytest -m parity`).

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict | ✅ clean |
| import-linter (strategy purity) | ✅ `strategies/` imports no infra/execution/IO |
| **parity gate** | ✅ 4 tests, zero mismatches |
| pytest (all) | ✅ 74 passed |
| frontend lint + build | ✅ clean |
| Playwright `stage-03` | ✅ 6 passed (3 cases × desktop + mobile) |
| **Full regression (stage 0–3)** | ✅ **50 passed** |

QA-3 cases: parity=0, determinism, warmup respected, indicator formulas, per-rule
triggers (fresh regime → EnterLong, regime-off → ExitAll, v5.2 never shorts),
strategy library UI + API manifest.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | Minor | Stray `//noqa` typo in a protocol docstring | Removed |
| 2 | Minor | mypy: pandas `Series`/`Index` typing on ATR + `to_period` | `pd.Series(...)` wrap, `pd.DatetimeIndex(...)` |
| 3 | Minor | Unit test asserted fresh-regime entry on the wrong bar (monotonic series transitions mid-history, not at the end) | Locate the actual regime-flip bar and test there |
| 4 | Trivial | pandas tz-drop warning in month grouping | `tz_localize(None)` before `to_period` (parity re-verified) |

No known open bugs.

## Scope note (honest)

The **decision engine** (`engine.py`) is the parity-anchored source of truth and is
fully validated bar-for-bar. The live `on_candle` adapter emits the correct intents for
the just-closed candle and is unit-tested for each trigger; its live execution semantics
(entry at next open, highest-high trailing over the live loop) are finalized and validated
against DEMO in **Stage 5** (bot lifecycle), where the loop drives the engine. This split
is intentional and matches the plan (Stage 3 = engine + parity; Stage 5 = live loop).

## Sign-off

Stage 3 meets its exit criteria: the CI parity job is green and mandatory; strategy
state is pure/deterministic. **Stage 4 (Risk & execution engines) requires the Binance
DEMO API key + secret to place test orders — I will request it before starting Stage 4.**
