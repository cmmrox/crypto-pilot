# Stage 8 — AI News Assistant (Codex SDK · GPT-5.5) — Report

**Status:** ✅ COMPLETE — QA gate passed, real GPT-5.5 briefing generated. **Date:** 2026-07-18.

## Scope shipped

The isolated daily briefing (FR-10) — informational only, never a trading input —
powered by the **Codex SDK with device-code login** (owner-driven, re-authenticatable).

- **Device-code auth** (`news/codex_auth.py`): `start_login()` returns a verification
  URL + user code; a background task awaits completion; the session persists under a
  mounted `CODEX_HOME` volume. `is_authenticated()`, `logout()`, and re-auth supported.
- **Provider** (`news/provider.py`): `SummaryProvider` protocol + `CodexProvider` that
  shells out to the `codex exec` binary (which uses the ChatGPT device-code session,
  unlike the SDK's `thread.run` which needs an API key) with `-m gpt-5.5` and
  `--output-last-message`, hard timeout + one retry, defensive JSON parsing.
- **Collector** (`news/collector.py`): CoinDesk / Cointelegraph / Bitcoin Magazine RSS +
  static FOMC/CPI calendar → URL-unique `news_items`; robust to feed failures.
- **Pipeline + scheduler** (`news/service.py`, `news/scheduler.py`): collect → summarise
  → publish one briefing/day (upsert), daily at the configured time + on-demand refresh.
- **API** (`api/news.py`): latest/archive/refresh + Codex login start/status/logout.
- **Frontend**: News view (briefing, sentiment, sources, macro calendar, isolation
  notice, archive) + Settings **Codex device-code panel** (Connect → shows URL + copyable
  code → polls to Connected; Re-authenticate + Disconnect).

## Live proof

Real briefing generated through the deployed stack via **`codex exec` + gpt-5.5** on the
owner's device-code session: 7 sourced bullets (BTC price action, MiCA/regulation,
stablecoin scrutiny, ETF flows, security risks, Asia consolidation, governance),
sentiment "Cautious". Device-code login completed by the owner in the browser.

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter (news isolation) | ✅ clean |
| pytest (unit + integration, isolated DB) | ✅ 131 passed |
| Playwright `stage-08` | ✅ 4 cases (news render, Codex panel, device-code start, isolation) |
| Deterministic regression (all stages) | ✅ 74 passed, 19 skipped (live suites) |
| Live | ✅ real GPT-5.5 briefing + device-code login verified |

QA-8: JSON parse (valid/embedded/garbage), pipeline publish, per-day idempotency,
**import-isolation from trading**, news view render, Codex connection state,
device-code start shows URL+code, API isolation contract.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | **Major** | CODEX_HOME volume owned by root; non-root `app` user couldn't init Codex state | Dockerfile entrypoint chowns the volume as root then drops to `app` via gosu |
| 2 | **Major** | SDK `thread.run(model=…)` hit `api.openai.com/v1/responses` (needs API key) — incompatible with the ChatGPT device-code session | Rewrote `CodexProvider` to shell out to `codex exec` (uses the ChatGPT session) |
| 3 | Minor | Deterministic news test hit real RSS feeds | `collect_first=False` for tests |
| 4 | Minor | Frontend not rebuilt with News/Codex views; lint (noqa/E501/SIM115) | Rebuilt image; lint fixes |

No known open bugs.

## Notes / decisions

- **Auth model:** device-code (ChatGPT session) via `codex exec`, per the owner's
  request — no `OPENAI_API_KEY` anywhere. Re-authentication and logout are first-class
  in the UI (`ARCHITECTURE.md §8`, `INTEGRATIONS.md §3`).
- The news module remains import-isolated from trading (contract enforced in CI + a
  runtime test).

## Sign-off

Stage 8 meets its exit criteria: scheduled + on-demand briefings work via device-code
Codex, isolation is enforced, and the owner can re-authenticate any time. **Stage 9
(Settings, security hardening, environment guard) needs no new keys — proceeding.**
