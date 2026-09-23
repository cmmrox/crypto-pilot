# Atlas 6 Trail — TradingView strategy

Copy all of `atlas_6_trail_strategy.pine` into a new TradingView Pine strategy.
Use standard **BINANCE:BTCUSDT.P, 4h** candles. Save and Add to chart. The Strategy
report and List of trades show the broker emulator's fills. This is a standalone
Pine v6 strategy, separate from the existing indicator editions.

## Included rules

- Long: close > SMA200 and EMA50 > EMA200; enter on a fresh bull regime or a
  below-EMA20 pullback followed by a close above EMA20, with pullback memory reset
  after a completed long. Confirm signals at the 4h close, fill at next open.
- Long initial stop 2.5 ATR; TP1 at 1R closes approximately 40% (quantity rounded
  down to the BTC step). After TP1, stop ratchets to max(previous stop, entry,
  highest high since entry minus 4.5 ATR), effective on subsequent price ticks.
- Long sizing: 15% equity risk, maximum 6x notional, estimated available-margin
  buffer. Qty is calculated at signal close, not the live execution mark.
- Short: close below SMA200 and EMA50 below EMA200, with close below
  SMA200 minus 0.5 ATR. Volatility-targeted 75% sleeve, 40% annualized target,
  span-48 unbiased exponential volatility. Resize at >20% rounded-quantity drift.
  Shorts have no price stop or fixed profit target; cover when deep-bear ends.
- Independent monthly long/short loss breakers: 4%, checked at 4h closes using
  simulated equity deltas. Reset on UTC month boundaries. A 4% trigger is not a
  guarantee of a maximum 4% loss.
- Initial simulated capital 1,000 USD; commission 0.05% per fill; zero slippage.
  Initial capital, fees and slippage can be changed under Properties.

## Read the chart

BUY and SHORT triangles identify decisions; native TradingView execution arrows
show simulated fills. SELL closes a long; COVER closes a short. TP1 sells part of
a long, not a short entry. Orange HALT crosses mark setups blocked by the selected
risk gates. The dashboard explicitly labels its position and gates as simulated.
Stop plots show the level submitted at that close for the next bar, not a stop
retroactively active during the current bar. Enable slow EMAs only if useful.

Use Strategy report → List of trades for dates, fill prices and quantities.
TradingView can count partial exits and short adds/reductions as separate records;
its trade count need not equal CryptoPilot's one-row-per-round-trip count.

## Comparing with LIVE

This script does not read Binance credentials, bot runs, fills, manual positions,
funding, balances, safe mode or the VPS monthly-halt ledger. Identical entry rules
do not imply identical executed trades. Starting capital, start date, chart history,
prior fills and costs change position state and monthly gates.

The optional **Apply manually verified halt window** setting is OFF by default.
Its example window is September 1 16:00 UTC through October 1 00:00 UTC, long only.
Enable it only to impose that known historical halt; this does not import account
state or reproduce earlier live trades. TradingView displays time inputs in its
selected timezone (Sri Lanka adds 05:30), despite the stored UTC timestamps.

For example, the August 7 20:00 UTC long can execute in this simulation even though
Binance rejected it in the real account. That changes subsequent August trades.
The default September simulation also halted longs after its September 1 trade.

## Explicit model differences

- Pine uses floating point; it cannot reproduce Python Decimal arithmetic exactly.
- Funding and liquidation are not modeled. Native margin checks are disabled;
  the script itself caps entry notional at 6x. TradingView's margin-call model is
  not Binance's isolated maintenance-margin model and must not be presented as one.
- Relative-tick protective brackets are submitted alongside entry so entry bars
  are protected without historical fill recalculation/lookahead. Subsequent stops
  use absolute tick-rounded prices. Initial prices can differ by a tick from live
  mark-based protection, and gaps change sizing/fill assumptions.
- TradingView's broker emulator decides intrabar stop/TP order. If both levels
  touch, it may differ from the Python replay's conservative stop-first rule.
- Fees default to one conservative rate for all fills; no maker/taker distinction.
- No VPS execution failures, manual interventions, deposit/withdrawal accounting,
  network outages or exchange rejection replay. No promised live parity.
- Loaded history can initialize indicators differently from the bot's rolling
  6,770-bar history. Standard 4h Binance perpetual candles are required.

Reference: TradingView's official strategy documentation:
https://www.tradingview.com/pine-script-docs/concepts/strategies/

## Verified September 22, 2026

The final 200-line Pine v6 file compiled and ran in TradingView on the requested
standard Binance perpetual 4h chart. Clipboard readback of the editor matched the
local file exactly (11,877 characters). The final instance produced 156 closed
trade records over the loaded January 2024–September 2026 simulation; this count
includes partial exits and is not a live-account trade count or profitability claim.
The chart visibly showed BUY fills, monthly-halt exits and blocked setup markers.
The older account-snapshot indicator was retained but hidden to avoid overlapping
signals. No script was publicly published and no exchange orders were sent.

Source validation: 27 refined-strategy/parity tests passed; one existing research
reference timezone warning. A separate 10,000-bar formula check matched the port's
ATR and unbiased exponential-volatility recurrences against pandas/runtime output
at tight numerical tolerances. These checks plus Pine compilation do not establish
full broker-emulator-to-live fill parity. Intrabar collision, gap and all resize
edge cases have not been exhaustively validated in TradingView.
