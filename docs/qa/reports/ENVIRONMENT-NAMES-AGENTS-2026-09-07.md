# Local environment display, strategy names and shared agent guidance

Scope: local fixes and regression only. Production was not accessed or changed for
this request, and no real exchange account was switched or order submitted.

## Findings and fixes

The Shell header contained literal `DEMO` / `Testnet funds` text. Settings used the
real `/api/bot/status` response, so LIVE could be correctly selected while the global
header incorrectly reassured the user that funds were simulated.

A session-scoped `TradingStatusProvider` now supplies both surfaces from one
server-confirmed status. It refreshes on mount, focus, every ten seconds and after
an accepted environment change. It fences old responses and invalidates in-flight
responses on teardown. Loading/error/unknown states never assume DEMO; unavailable
status disables switching. LIVE receives red treatment and the Real funds label.
The Start dialog's separate DEMO fallback was also removed; unavailable or stale
overview data disables starting until the snapshot is verified again.

Human-facing names now come from strategy manifests:

- Atlas 5.2 · 4h — existing long-only fallback.
- Atlas 6 · 4h — existing long/short baseline.
- Atlas 6 Trail · 4h — existing wider-trail variant.

Machine IDs, aliases, software releases and strategy parameters remain unchanged.
The overview API adds `strategy_display_name` alongside the stable ID, and the
strategy watch renders that display name. Existing persisted trades are untouched.
New names are product labels, not profitability claims or LIVE approval.

## Shared project guidance

`AGENTS.md` and the relative `CLAUDE.md` link share one bootstrap.
`.agents/skills/cryptopilot-dev/SKILL.md` and the relative Claude skill link share
one canonical body. These paths already resolved within this checkout; no external
copy or credential relocation was necessary. The skill now routes both tools to
`docs/strategies/NAMING.md` and `docs/guidelines/AGENT_SETUP.md`.

The naming guide defines family/generation/variant names, stable machine identity,
separate software-release metadata and the prohibition on implied safety/performance
claims. The creation guide and template use it. Repository containment checks reject
agent paths or required references resolving outside the checkout. Both the valid
setup and an intentionally external symlink rejection were tested. The general
skill validator also passed. No project skill was written outside the repository.

## Verification

- Full backend suite, including parity: 325 passed, three credential-dependent
  exchange tests skipped; no trading math changed.
- Relevant desktop/mobile browser regression: 56 passed, ten skipped (eight real
  exchange lifecycle cases and two mobile-only omissions covered on desktop).
- Frontend lint, TypeScript, seven unit tests and production build passed.
- Backend strict mypy: 91 source files passed. Ruff and formatting passed.
- Focused new API and browser assertions additionally cover names, stable IDs,
  overview display labels, LIVE reload, confirmed switches, rejected switches,
  unavailable status and focus refresh recovery.

LIVE browser scenarios intercept only the relevant account-status/mutation responses
in the isolated local QA app. They verify rendering and synchronization without
activating LIVE trading. They do not certify production exchange or SMS behavior.

Final focused results: four API contract tests passed and all twelve desktop/mobile
browser tests for environment state, recovery and named strategy selection passed.
A local mobile screenshot confirms the red LIVE / Real funds header agrees with the
LIVE Settings selection. The new snapshot field is covered by the overview API
contract. These focused checks followed the broader regression above.

Regression sensitivity check: temporarily restoring the old hardcoded DEMO header
made ENV-01 fail specifically with `DEMOTestnet funds` while Settings showed LIVE.
After restoring the fixed source, the same case passed again. No temporary fault
was retained. All changes and test artifacts were confined to the local repository.
