# Clean Code Management

The bar: any file you touch, a stranger can understand in one read. These rules apply
to both stacks; language specifics live in `BACKEND_GUIDELINES.md` /
`FRONTEND_GUIDELINES.md`.

## Principles

1. **Name things by domain language.** `sleeve_month_pnl`, `deep_bear`, `warmup_bars`
   — the BSD's vocabulary is the code's vocabulary. No `data2`, no `helper`, no
   `utils.py` dumping grounds.
2. **Small units, single purpose.** Functions do one thing; ~40 lines is a smell
   threshold, not a law. A function needing 6 arguments wants a dataclass.
3. **Explicit over clever.** No magic numbers — validated strategy constants live in
   the pinned params; everything else is a named constant with a comment saying *why*
   that value. No metaprogramming where a plain function works.
4. **Comments explain why, not what.** The what is the code. Preserve the research
   rationale comments (e.g. *why the short has no stop*) — they prevent well-meaning
   "fixes" that destroy the validated edge.
5. **Delete, don't hoard.** Dead code, commented-out blocks, unused deps and feature
   flags are removed on sight — git remembers.
6. **Duplication rule of three:** copy once is fine, twice is a warning, third time
   extract — but only extract when the duplicates are the *same concept*, not merely
   the same shape.
7. **Boy-scout, bounded.** Leave touched code slightly better; don't turn a fix PR
   into a refactor PR — refactors ship separately (see `CODE_REVIEW.md`).

## Structure smells that fail review

- Business logic in routers/components; I/O inside `strategies/`; cross-module reach
  (importing another module's internals instead of its interface).
- Try/except that swallows; broad exceptions off loop boundaries; return-`None`-on-
  error instead of raising.
- Float money, naive datetime, string-built SQL, hand-rolled crypto.
- Copy-pasted prototype JSX with dead props instead of a properly ported component.

## Formatting & mechanics

Formatters are law (ruff format, Prettier) — zero formatting debates in review.
Imports ordered/deduped automatically. File encoding UTF-8, LF endings.

## Refactoring policy

Refactors are welcome, gated: behaviour-preserving, covered by tests before the
refactor starts, own PR labelled `refactor:`, and never within Stage 3–4 strategy/
execution code without re-running the parity suite.
