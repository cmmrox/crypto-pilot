# Strategy names

Owner-facing names identify a strategy family, generation and optional behavior
variant, similar to a model product line. They do not imply profitability or LIVE
approval. The manifest `display_name` is the sole source for UI labels.

| Display name | Stable strategy ID | Software release | Behavior |
|---|---|---|---|
| Atlas 5.2 · 4h | `trend_rider_v52_4h` | 5.2 | Long-only fallback |
| Atlas 6 · 4h | `trend_rider_v6_4h` | 6.0 | Long and short baseline |
| Atlas 6 Trail · 4h | `trend_rider_refined_v1_4h` | 1.0 | Atlas 6 with a 4.5 ATR long trail |
| Atlas 7 Dual · 4h | `atlas_dual_v1_4h` | 1.1 | Trend pullback + squeeze breakout, stops both sides |

## New strategies and releases

- Use `<Family> <Generation> [Variant] · <interval>` for `display_name`. Keep the
  family short and pronounceable; use the same family for related implementations.
- Choose a variant word that describes behavior (for example `Trail`), rather than
  implementation history (`refined`, `new`, `final`) or claims (`best`, `safe`, `live`).
- Keep the product generation separate from `manifest.release`: a variant can have
  its own 1.0 release while belonging to generation 6. Show release details separately.
- Allocate a unique machine ID and matching filename using the creation guide.
  Never rename an existing ID, alias, persisted trade or bot run for a display rename.
- Keep symbol, direction, risk and validation in manifest fields and explanatory
  text. A name is not a validation certificate or permission to start trading.
- Render manifest names in selectors, confirmations, overview and research screens.
  Keep machine IDs for API/storage and secondary technical details. Do not maintain
  duplicate frontend name maps or infer a display name by formatting an ID.
- Update the catalog above, API/browser assertions and validation evidence when
  adding a named release. Historical QA reports retain the names observed then.
