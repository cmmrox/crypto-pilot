# Dashboard Command Center — Design QA

## Evidence

- Source visual truth: `docs/design/dashboard-command-center-reference.png`
- Browser-rendered implementation: `docs/design/dashboard-command-center-implementation.png`
- Combined comparison input: `docs/design/dashboard-command-center-comparison.png`
- Responsive evidence: `docs/design/dashboard-command-center-mobile.png`
- Route: `http://localhost:8090/overview`
- Desktop viewport: 1672 × 941
- Mobile viewport: 390 × 844
- State: authenticated owner, DEMO, bot running, flat account, live Binance public
  market observation, current stored news briefing

The source and desktop implementation were captured at the same viewport without
browser chrome, then vertically combined into one image before review.

## Comparison History

### Pass 1 — blocked

- **P2 — Above-the-fold density drift.** The visible page heading consumed a row that
  the source gives to operations, pushing account and guardrail content below the
  viewport.
- **P2 — Account metrics stacked vertically.** The missing command-center grid rule
  rendered four metrics as full-width rows instead of the source's scan-friendly
  four-column strip.

Fixes:

- Preserved the semantic `h1` for accessibility while visually collapsing the heading
  copy and keeping lifecycle controls in the source-aligned top row.
- Added the four-column metrics grid with two-column and one-column responsive
  fallbacks.
- Tightened news typography and fixed the first dashboard row height so the strategy,
  account, position, and guardrail hierarchy follows the selected screen.
- Re-captured the implementation at 1672 × 941 and rebuilt the combined comparison.

### Pass 2 — passed

The revised combined evidence has no actionable P0, P1, or P2 difference. The
implementation intentionally uses three compact strategy-rule cards instead of the
mock's three full-width rows; the same conditions, status, price threshold, distance,
and warning are present, and the denser treatment keeps more owner state above the
fold without changing hierarchy or meaning.

## Required Fidelity Surfaces

- **Fonts and typography:** Existing system UI stack, weights, compact labels, numeric
  hierarchy, and tabular countdown remain coherent with the product and selected
  reference. No clipping or unintended truncation was observed.
- **Spacing and layout rhythm:** Sidebar, top bar, control rail, three-column command
  grid, status cards, borders, radii, and section gaps align with the reference's dense
  control-room treatment. Desktop and mobile have no horizontal overflow or overlap.
- **Colors and tokens:** Existing CryptoPilot background, panel, border, amber,
  green, and red tokens map consistently to neutral, healthy, caution, and emergency
  states. Text and state contrast are legible.
- **Image quality and assets:** The screen requires no photography or illustration.
  Existing brand and Lucide product icons remain sharp and consistent; no placeholder
  imagery, custom SVG substitution, emoji, or CSS illustration was introduced.
- **Copy and content:** Heartbeat wording distinguishes bot lifecycle from real worker
  liveness. Price thresholds are explicitly closed-candle conditions, not promised
  orders. News is visibly read-only and never a trading input.
- **Responsive behavior:** At 390 × 844 the lifecycle controls, engine checks, market
  price/chart, countdown, and downstream cards form a usable single column. The mobile
  navigation opens and closes correctly.

## Interaction and Runtime Checks

- Authenticated desktop and mobile rendering
- Mobile navigation open/close
- Safe-stop confirmation open/cancel with no mutation
- Four-second refresh, single-flight request behavior, and explicit failed-refresh
  stale state
- Loading, account-unavailable, market-stale, flat-position, and strategy-warmup
  fallbacks
- Console errors and warnings checked in the in-app browser: none

Focused region comparison was not needed after the second pass because all text,
icons, controls, and state labels were readable at original resolution in the combined
1672-pixel-wide evidence.

## Findings

No remaining P0, P1, or P2 findings.

## Follow-up Polish

- P3: A future table-density preference could switch the three strategy cards to the
  mock's full-width rows, but the current implementation is more compact and does not
  reduce owner comprehension.

final result: passed
