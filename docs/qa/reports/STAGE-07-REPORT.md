# Stage 7 — Notifier (notify.lk SMS) — Report

**Status:** ✅ COMPLETE — QA gate passed, real SMS delivered. **Date:** 2026-07-18.

## Scope shipped

Every significant event reaches the owner's phone.

- **Gateway** (`notifier/gateway.py`): `SmsGateway` protocol + `NotifyLkGateway` (HTTP to
  `app.notify.lk/api/v1/send`) + `FakeSmsGateway` (tests).
- **Templates** (`notifier/templates.py`): the full BSD §10 set, 320-char cap, safe on
  missing keys.
- **Service** (`notifier/service.py`): event → SMS, fire-and-log with 3 retries, updates
  event `sms_status`, never raises (trading never blocked).
- **Config + helper** (`services/notify_config.py`): encrypted notify.lk config
  (user_id/api_key/sender_id/phone) + `notify_event(...)` that no-ops when disabled or
  unconfigured.
- **Wiring**: SMS on bot start/stop and long/short trade opens.
- **Settings API** (`api/settings_api.py`): save config, status, enable/disable toggle,
  real test-SMS.
- **Frontend SMS panel** (`views/Settings.tsx`): config form (write-only key), delivery
  toggle, test-SMS button.

## Test run summary

| Gate | Result |
|---|---|
| ruff / mypy strict / import-linter | ✅ clean |
| pytest (unit + integration, isolated DB) | ✅ 125 passed |
| Playwright `stage-07` (incl. `RUN_LIVE_SMS=1`) | ✅ 4 passed |
| **Live delivery** | ✅ **real SMS delivered to the owner's phone** (verified twice) |
| Deterministic regression (all stages) | ✅ 66 passed, 19 skipped (live suites) |

QA-7 cases: template rendering (values, no-stop wording, missing-key safety, 320-cap),
retry-then-recover, exhausted-retries-never-raise, disabled toggle, SMS panel configured
state, delivery toggle, status API, real test SMS.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | Minor | `BaseModel`/`Field` not imported in settings_api after adding inline schemas | Added imports |
| 2 | Minor | Long lines in templates/settings/notify_config | Reflow + per-file E501 ignore for the SMS template strings |

No known open bugs.

## Review notes

- Dependency inversion at the SMS boundary (protocol + fake + live), fully mock-tested
  then live-validated. Fire-and-log guarantees trading is never blocked by SMS.
- notify.lk config stored AES-GCM encrypted (write-only, phone shown as a masked hint).

## Sign-off

Stage 7 meets its exit criteria: real SMS received for bot/trade events; delivery
status is audited; failures never block trading. **Stage 8 (AI news via Codex SDK) is
next — the owner requested a device-code login flow with re-authentication in the UI;
implementing that now.**
