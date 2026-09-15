# Live strategy and matching replay audit — 2026-09-14

## Verdict

The observed September inactivity follows the configured strategy and monthly risk
policy. No missed actionable decision or execution failure was found in the audited
window. No production code, settings, breaker state, orders or services were changed.
This establishes observed decision correctness, not future execution or profitability.

## Fresh production evidence

VPS `/home/cmmrox/crypto-pilot` is clean at `e0bf690`. Backend image is
`sha256:bbd4c250de94c9165a2bb676b089d45de57780acfebb58627482f49e4444592b`,
with zero restarts. Deep health at approximately 18:12 UTC reports healthy database,
worker and scheduler, with no overdue ingestion. Local and VPS checkout SHA-256s match
for BotService and the shared original/refined strategy implementations.

Active configuration: LIVE, `trend_rider_refined_v1_4h`, release 1.0, display name
**Atlas 6 Trail · 4h**. Current run 14 began September 7 at 08:22:45 UTC; run 13
used the same release earlier that day. Run 14 has no stop reason or stop timestamp.
Its latest evaluated candle opened September 14 at 12:00 UTC and closed at 16:00 UTC
(21:30 Sri Lanka). The 16:00–20:00 UTC candle was still open during inspection.

The release differs from original v6 only in the 4.5 ATR long runner trail. It retains
15% long risk sizing, 6x leverage cap, independent 4% monthly loss breakers, closed
4h entries and the stop-free, volatility-sized short sleeve.

Signed Binance read-only account and order requests confirmed:

- Wallet/available balance: 190.18202024 USDT; unrealized PnL: zero.
- No nonzero positions; zero regular and conditional open orders across the account.
- September BTCUSDT fills: one BUY of 0.014 at 78,535.70, September 1 00:00 UTC;
  one SELL of 0.014 at 77,901.90, September 1 16:00 UTC. No later fills through inspection.
- Persisted trade 13 matches those fills. Gross PnL -8.87320000, fees 1.09506320,
  funding -0.15195302: net loss **10.12021622 USDT**.

## Why no new trades

On September 1 at 16:00:23 UTC, event `breaker:LONG:2026-09` latched the long halt.
Its recorded monthly loss was 8.90813109 against starting marked equity
199.79372153: **4.458664%**, beyond the 4% limit. The market exit and its fee occurred
subsequently, so the trigger's marked loss differs from the final realized net loss.
The threshold is evaluated at candle boundaries; it is not a guaranteed maximum loss.

The monthly halt persists across stop/start and strategy selection. Choosing the
refined trail does not erase September's long losses. The short breaker was false.
The normal monthly reset is October 1, 00:00 UTC (05:30 Sri Lanka); an entry still
requires the strategy's conditions and all runtime gates to pass at that time.

All 46 retained decision observations since September 7 have `entries_allowed=true`,
`halted_long=true`, `halted_short=false` and no emitted intent. There are two observations
for run 13 and 44 consecutive four-hour observations for run 14, without missing bars.
Their `NO_SIGNAL` outcome is post-risk-state strategy output; it does not mean there
were no bullish market setups.

Counterfactual evaluation of each *same flat live state* with halts removed produced
six long intents: September 9 at 08:00 and 12:00 UTC, and September 14 at 04:00,
08:00, 12:00 and 16:00 UTC. These are six qualifying evaluations, not six independent
trades in a continuous unhalted simulation. No short intent qualified.

At the latest close, price 78,543.10 was above SMA200 74,809.34 and EMA50 77,854.47
was above EMA200 75,171.25. That is a bull regime, incompatible with the required
deep-bear short conditions. The long pullback-resumption condition qualified but was
blocked by the existing monthly long halt.

## Exact decision reproduction and backtesting

Retained safe artifacts are under `.artifacts/strategy-audit-2026-09-14/` (untracked
local evidence, not committed account data). Export scripts use read-only database
transactions and allowlisted fields; credentials remain within the VPS container.

1. `compare.py` reconstructs each observation's full 6,770-bar history, checks its
   SHA-256, and invokes the production public `on_candle` with recorded TradeState.
   **46/46 history hashes match; 46/46 intent lists match exactly.**
2. A fresh public Binance fetch matches all OHLCV values for **99/99 closed candles**
   against the database, including the latest. The forming candle is excluded.
3. `backtest.py` uses the pinned refined parameters, live exchange filters, actual
   public funding, 0.05% per-side fee assumption matching the observed fills, and the
   chronological production plugin replay with next-open simulated fills.

| Comparison | Starting equity | Ending equity | Closed trades | Ending position |
|---|---:|---:|---:|---|
| Actual run 14 | 190.18202024 | 190.18202024 | 0 | Flat |
| Replay initialized with the live September halt | 190.18202024 | 190.18202024 | 0 | Flat |
| September 1 flat-start refined replay | 200.30223646 | 189.64449443 | 1 long | Flat |
| Actual September account | 200.30223646 pre-entry | 190.18202024 | 1 long | Flat |

The inherited-state replay covers 43 full execution bars from September 7 12:00 to
September 14 12:00 UTC. It has zero PnL, drawdown and trading costs, and no intents.
The exact observation comparison additionally covers the latest 16:00 UTC decision,
whose following execution bar is still forming and therefore excluded from the OHLC
backtest. The halt was seeded, so the replay reports zero *new* breaker trips.

The September flat-start replay opens September 1 at 00:00 and closes at 16:00 for
`monthly_breaker`, with no later entries. Net PnL -10.65774203; simulated maximum
marked drawdown 5.7492%. Simulated entry/exit are 78,549.60 / 77,877.40 versus live
78,535.70 / 77,901.90. These price differences explain the roughly 0.5375 USDT
ending-equity difference; funding and fees are included. It is not exact fill parity.
This short window is for behavior verification, not strategy ranking.

The month replay deliberately applies refined throughout September for comparison;
the live September 1 trade used original v6. The sole 4 versus 4.5 ATR runner-trail
change does not affect that trade's breaker exit. The exact observed-state comparison
uses each actually recorded strategy identity.

## Verification and limits

Command:

```sh
PYTHONPATH=backend backend/.venv/bin/python -m pytest -q \
  backend/tests/parity backend/tests/unit/test_refined_strategy.py \
  backend/tests/integration/test_refined_release.py \
  backend/tests/integration/test_bot_lifecycle.py
```

Result: **50 passed**, one existing research pandas timezone-to-period warning.
No research files were changed. No synthetic order was placed to test execution.
September 1 live fills demonstrate prior execution, while present flat state cannot
certify a future entry/stop/partial-fill lifecycle. Decision telemetry begins with
the September 7 release; earlier behavior is supported by trade, breaker, equity,
ingest and exchange evidence rather than an equivalent full observation record.
The pre-existing dirty production report and untracked `tradingview/` were preserved.
