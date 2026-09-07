# UI/UX Guidelines

The design system is **defined by the approved prototype** (`prototype/final-cryptopilot`
— run `npm run dev` to see it). These rules capture its intent so ports and new
surfaces stay coherent.

## Design language

- **Dark control-room aesthetic:** near-black layered surfaces, 1px hairline borders,
  amber brand accent (Bitcoin gold), green=positive/healthy, red=negative/danger,
  amber=caution/attention. Geist (text) + Geist Mono (numbers, codes, IDs).
- **Numbers are the product.** Tabular figures, mono for prices/quantities/IDs,
  explicit signs (`+`/`−`), currency and units always shown, 2-decimal money / 8-max
  quantity precision. Positive/negative always tone-colored *and* signed.
- Hierarchy pattern per panel: `KICKER` (small caps, muted) → title → content → fine
  print. Keep it — it's what makes dense screens scannable.

## Trust & safety UX (the soul of this app)

1. **Truth over reassurance.** Show the real state: safe mode, reconnecting, stale
   data, degraded SMS — with banners, never silently. A frozen number styled as live
   is a bug (use the `Streaming` badge / staleness pattern).
2. **Guarded actions.** Anything irreversible or money-touching uses the confirmation
   modal: tone (warning/danger), consequence list, and typed confirmation for the
   gravest (`LIVE`, `FLATTEN`). Cancel is always available and unambiguous.
3. **Explain the strategy's behaviour in place.** The no-price-stop short callout,
   breaker meters with thresholds, "decisions only on closed 4h candles" — keep this
   educational layer; the owner should never wonder *why* the bot did something.
4. **Honest risk framing.** Performance claims always carry the caveat (fees included,
   past ≠ future). Never invent precision the data doesn't have.
5. **Environment always visible.** Header and Settings share the server-confirmed
   trading account status. Loading or failed reads must never assume DEMO; show
   Checking/Unavailable and disable environment switching until verified.
   The DEMO/LIVE badge stays in the header on every
   screen; LIVE gets the danger treatment everywhere it appears.

## Interaction patterns

- Navigation: fixed sidebar (6 views) + settings tabs — as prototyped. Page heading
  carries context (kicker/title/description) + the view's primary actions.
- Drawers for detail (trade round-trip, event payload); modals for decisions; toasts
  for confirmations (title + one-line consequence). Escape closes topmost layer.
- Empty/loading/error states designed for every surface (prototype pattern: icon,
  headline, remedy action).
- Live updates animate subtly (fade/tick, no layout shift). Charts: no animation on
  data refresh (`isAnimationActive={false}` pattern) to keep them honest.

## Responsive & accessibility

- Breakpoints as prototyped: desktop grid → single column; sidebar becomes an overlay
  with scrim at mobile; 390px width must have zero horizontal overflow.
- Touch targets ≥40px; keyboard path through every flow; focus visible; contrast ≥
  WCAG AA for text and state colors; `aria-label` on all icon-only buttons;
  `role="dialog"`/`aria-modal` on overlays (already prototyped — keep it in the port).

## Writing style (microcopy)

Calm, specific, operator-grade. Say what happened and what happens next
("Reduce-only cover submitted; the bot stops after Binance confirms the fill"), not
marketing fluff. UTC-label timestamps. Sentence case except KICKERS.
