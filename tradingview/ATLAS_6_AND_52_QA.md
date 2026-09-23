# Atlas 6 and Atlas 5.2 Pine strategies — September 22, 2026

## Deliverables

- `atlas_6_strategy.pine`: production `trend_rider_v6_4h` release 6.0; long and short; 4 ATR runner.
- `atlas_52_strategy.pine`: production `trend_rider_v52_4h` release 5.2; long only; 4 ATR runner.

Use standard BINANCE:BTCUSDT.P 4h candles. Copy the entire file into a separate
Pine Editor strategy, save, and Add to chart. Open Strategy report and List of
trades. Existing `STRATEGY_GUIDE.md` describes the shared simulation, except that
these releases use 4 ATR rather than Trail's 4.5 ATR; Atlas 5.2 never opens shorts.
Both use a 2.5 ATR initial long stop, 40% rounded partial at 1R, 15% risk target,
6x sizing ceiling and monthly 4% loss gates. Simulated initial capital is 1,000;
commission 0.05% per fill, slippage zero. These are not live Binance histories.

## Completed QA

Both complete source files were pasted into TradingView Pine Editor and compiled
successfully on the Binance perpetual 4h chart. Editor clipboard readback exactly
matched each local file; Atlas 5.2 was recompiled after its final display update.

Atlas 6 produced 155 simulated closed records on the loaded January 2024–September
2026 history. Report signal breakdown contained BUY, SHORT and Short add. Inspected
its first short entry/cover and long partial/runner records. For example the
February 8 long's partial exited February 9 at 45,649.6 and its runner exited
February 21 at 50,528.4 (chart timestamps displayed in Asia/Colombo).

Atlas 5.2 produced 64 simulated closed records over the same selected period.
The report's entire signal breakdown contained BUY only. Its first long partial
and runner records match the Atlas 6 long prices/times noted above. Source inspection
also confirms no `strategy.short` instruction remains in Atlas 5.2. Both compiled
without a displayed compiler/runtime error. Trade counts include partial exits,
not necessarily independent round trips. Backtest returns are not live evidence.

Local source gates:

- Refined strategy plus research parity: 27 passed, one existing research timezone warning.
- Strategy unit tests and public/prepared entrypoint parity: 20 passed.
- Exact Atlas 6/Trail source comparison: only identity/labels and 4 versus 4.5 ATR differ.
- Atlas 5.2: 4 ATR trail present, no short order instruction, entry setup disabled for shorts.
- `git diff --check`: passed (new files additionally inspected directly).

## Important limits

This is compilation, chart execution, source mapping and focused behavior QA,
not a certification of complete Pine/Python trade-for-trade parity. Funding,
liquidation, exchange rejection, operational safe mode and real account state are
not simulated. Native margin calls are disabled; code caps entry sizing itself.
TradingView decides intrabar order paths; dual stop/TP touches can differ from
Python's stop-first replay. Quantity is sized at signal close; entries fill at the
next open. EMA initialization, fees, gaps and account-dependent monthly gates can
therefore change trades. All intrabar/gap/resize edge cases were not exhaustively
exercised in TradingView. Do not connect these scripts to automated live execution
on the strength of this QA.

Chart management: saved scripts were preserved; temporary strategy instances were
removed to respect the TradingView plan limit. Atlas 5.2 is the final active chart
strategy, with the earlier manual-account indicator retained hidden. No production
bot, strategy selection, exchange order or VPS setting was changed.
