# Atlas 6 Trail for TradingView

Open `atlas_6_trail.pine`, copy the entire file into a blank TradingView Pine
Editor indicator, save, and choose **Add to chart**. Use standard candles on
**BINANCE:BTCUSDT.P**, **4h**. The script rejects other timeframes and synthetic
chart types. Load at least 200 bars before expecting signals; more history improves
EMA initialization agreement. The start-date input controls modeled trades, not
indicator warm-up. Changing chart history or this date can change modeled positions.

This is a Pine v6 **indicator**, with a chart trade model, not a Strategy Tester
backtest or an exchange connection. It does not place orders.

## Rules traced to the current release

Source: `packages/strategy_runtime/src/strategy_runtime/refined_trend_rider.py`,
`trend_rider.py`, `parameters.py`, `indicators.py`, and `replay.py`.
The strategy ID is `trend_rider_refined_v1_4h`, release 1.0.

| Event | Rule |
| --- | --- |
| Bull regime | Close > SMA200 and EMA50 > EMA200 |
| BUY setup | Flat, bull regime just began, or price closed back above EMA20 after a below-EMA20 close during this bull regime while flat |
| Long entry | Following candle open; use the signal candle's ATR14 |
| Initial SL | Entry minus 2.5 × signal ATR |
| TP1 | Entry plus 2.5 × signal ATR (1R); sell 40% |
| Runner | Remaining 60%; no fixed TP2 |
| Runner SL | After TP1: max(previous SL, entry, highest high since entry − 4.5 × current ATR); active next bar |
| Sell long | Active SL touches, or bull regime ends (next-open exit) |
| SHORT setup | Flat; close < SMA200, EMA50 < EMA200, close < SMA200 − 0.5 × ATR |
| Short target | 75% × min(1, 40% / annualized realized volatility), shown as percent of equity |
| Cover short | Deep-bear condition ends; following candle open |
| Short SL / TP | None; the deep-bear boundary is not a stop order |

The short volatility calculation uses unbiased exponential variance of simple
returns, span 48, annualized with sqrt(2190). The ATR uses the runtime's first-valid
true-range exponential seed, instead of Pine's SMA-seeded `ta.atr()`.
Parameters are pinned to Atlas 6 Trail; the inputs change only presentation and
when the chart model starts.

## Read the chart

- Green triangle **BUY SETUP**: a closed-candle decision. The **BUY** price label
  is on the following bar's open. Red **SHORT SETUP** and **SHORT** work similarly.
- Aqua: modeled entry. Red: stop active during that bar. Green: outstanding TP1.
- **TP1 SELL 40%**: partial exit. The position panel switches to the 60% runner.
- Orange dots: a newly calculated SL that becomes active on the following bar.
  Breakeven is the entry price before costs, not a guarantee of zero net loss.
- **SELL** closes a long; **COVER** closes a short. They are not interchangeable
  with opening a new short or long.
- Green/red shading describes bull/deep-bear conditions. It and moving averages
  can change during the forming candle; setup decisions only occur at its close.
- The panel shows modeled position, pending action, prices and latest event.
  TradingView retains at most the latest 500 event labels; historical level plots
  and setup markers remain subject to available chart history.

For example, entry 100,000 and signal ATR 1,000 means initial SL 97,500 and
TP1 102,500. After TP1, if highest high is 110,000 and current ATR is 1,500,
the candidate trail is 103,250. The actual next stop is the maximum of that,
the existing stop and entry; it can never decrease.

## Alerts

Create an alert, select this indicator and the desired named condition, and set
**Once Per Bar Close**. BUY/SHORT setup alerts arrive at the signal close.
Modeled entry/exit confirmation alerts and SL/TP touch alerts arrive at the close
of the candle containing the modeled fill. They are educational confirmations,
not real-time protective orders. Create separate alerts for the events wanted.
Changing script inputs requires recreating alerts with those settings.

## Modeling limits

- No portfolio simulation: **independent 4% monthly loss breakers are not applied**.
  The actual bot can reject entries or close positions that this chart model keeps.
- The actual long sizing profile is 15% equity risk, capped at 6x leverage. This
  script does not size longs. A 4% monthly breaker is not a maximum loss guarantee.
- Short target weight is informational. The bot uses equity, next-open prices,
  rounded quantities and a >20% drift threshold to resize; this script does not
  simulate those fills, their changing average entry or their P&L.
- Fees, funding, slippage, liquidation, exchange rounding/minimums, account state,
  operational breakers, manual orders and reconciliation are not represented.
- At candle close the model checks the SL that was active during that bar before
  checking TP1. If both touched, **SL wins**, consistent with the conservative
  production-plugin candle replay. Real intrabar order cannot be known from OHLC.
  Stop gaps fill at the lower open; TP gaps at the higher open. Trail updates do
  not use a candle's high to stop out against that same candle's earlier low.
- No intrabar TP/SL alerts are emitted before candle confirmation. Pending market
  fills appear at the next open and are replayed consistently under Pine rollback.
- Chart feed, loaded-history start, Python rolling history, floating-point math
  and exchange precision can produce boundary differences. This port is not
  certified for bar-for-bar bot parity or profitable/live operation.

## Verification

The source release tests and parity suite are run separately from Pine verification.
They verify the Python source, not compilation or execution of this Pine port.
There is no local TradingView compiler in this repository. Pine Editor compilation
and visual chart acceptance are still required; do not interpret source checks as
an executed TradingView test.

Chart acceptance checks:

1. Add on standard BTCUSDT perpetual 4h candles; wrong timeframe/chart types fail.
2. Inspect a fresh bull entry and a later EMA20 pullback entry. Setup precedes fill.
3. Check entry ± 2.5 × signal ATR against Data Window values.
4. Find TP1: 40% is marked once, runner persists, SL never moves down or acts early.
5. Check an SL/TP dual-touch bar: SL wins; no TP marker should appear.
6. Inspect a regime exit and a short: cover follows bear-condition failure,
   with no invented short SL or fixed TP.
7. On a forming candle, setup and touch alerts wait for close; modeled pending
   open fills remain stable after reload with the same history and settings.

Pine API references: [bar states](https://www.tradingview.com/pine-script-docs/concepts/bar-states/),
[alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/), and
[v6 reference](https://www.tradingview.com/pine-script-reference/v6/).

Local verification on 2026-09-07:

- `cd backend && .venv/bin/python -m pytest tests/unit/test_refined_strategy.py tests/parity -q`:
  **27 passed**, one existing timezone-to-period warning in the research reference.
- Compared the port's ATR and unbiased EWM volatility recurrence formulas with
  runtime/pandas outputs over 10,000 deterministic synthetic bars: passed
  (`rtol=1e-12`, ATR `atol=1e-9`, volatility `atol=1e-12`). This checks formulas,
  not Pine's compiler, trade-state execution, chart visuals or alerts.
- Self-review covered next-open entry ATR anchoring, stop-before-TP ordering,
  delayed trail activation, flat-only pullback memory, and no short price stop.

## Clean chart edition

Use `atlas_6_trail_clean.pine` for the simplified presentation. Replace the entire
Pine Editor contents with this file and remove the older indicator from the chart
so the two overlays do not stack.

Defaults: EMA20 and SMA200 only, no regime background, small modeled fill markers,
300 bars of visible trade drawings, faint entry/SL/TP shading, current price tags,
and a compact bottom-right dashboard. Colors adapt in part to the chart theme and
trade colors can be customized. Right-side tags may require extra chart margin.
`SL / BE` combines the entry and stop tag when the stop equals entry.
`NEXT SL` is offset farther right to distinguish it from the active stop.

Choose **Study** to show EMA50, EMA200, the deep-bear boundary and small setup dots.
Enable **Detailed event labels** for the earlier verbose fill descriptions; this
replaces the small fill markers. Changing visible-history length only affects
presentation, never trade evaluation or alerts. The same chart-model limitations
and closed-bar alert timing described above apply to both editions.

Clean-edition source check: calculation and position-state sections compared
unchanged to the original, excluding the drawing helper; alert section identical.
Pine Editor compilation and visual acceptance on TradingView remain unverified.
Suggested visual checks: dark/light charts, all four dashboard corners, Clean/Study,
flat/long/runner/short states, entry=stop tag, nearby active/pending stops, and
removing the older overlay before assessing the new layout.

## Account-aware signal companion — September 14 correction

Use `atlas_6_trail_account_signals.pine` to distinguish market setups from the
manual account gates. This replaces fictional chart positions with an explicit
manual snapshot; it is not an automatic VPS mirror or a complete backtest.
Remove the earlier chart-model overlay before adding it.

Defaults reflect audited run 14: flat, long monthly halt active, short halt inactive,
entry gates open; validity begins September 7 08:22:46 UTC. The locally chosen
expiry is September 15 18:12 UTC (24 hours after the audit), not a Binance guarantee.
Update the position/gates immediately after any account change and recreate alerts.
The script requires a renewed snapshot at a UTC month boundary even if the entered
expiry is later. It does not independently calculate monthly PnL or reset live risk.

Six qualifying September 9/14 long evaluations are labeled LONG BLOCKED. It creates
no modeled BUY, entry or target from them. Eligible labels mean only that the pure
setup passes manually supplied gates; they never certify an order or fill. Repeated
setups can appear while the manually entered position stays Flat. Other live gates,
exchange sizing, short rebalancing, fees, funding and tick rounding remain outside
this companion. Unknown state suppresses eligible signals. Gray historical markers
outside the validity window are intentionally unverified.

For an actual open position, enter its confirmed entry and long SL/TP levels.
These values are displayed as supplied; no fill or stop touch is inferred. For a
long runner, enter TP1 filled and highest high since entry to display a 4.5 ATR
stop candidate at confirmed closes; the candidate is not an exchange amendment.
Refresh the actual highest high and stop after each management update.

Local September 14 validation reconstructed the recurrence and manual gates against
44 recorded run-14 states: 44 matching empty intent lists, six blocked long setups,
zero eligible entries. Start/expiry/month-boundary checks passed. This is Python
formula and gate evidence, not a Pine compiler or chart-execution test. TradingView
compilation and visual acceptance remain unverified. Inputs follow TradingView's
[time-input contract](https://www.tradingview.com/pine-script-docs/concepts/inputs/).
