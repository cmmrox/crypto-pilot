# SMS 2FA Implementation Plan

**Implementation status (2026-07-19):** implementation and expanded automated
coverage are present on `feature/sms-2fa`; evidence and remaining release gates
are recorded in `docs/qa/reports/SMS-2FA-REPORT.md`. The stage is not released
or closed: the fixture-backed container regression and final exact-snapshot
security scan must pass on the reviewed commit, and production promotion
remains prohibited by the Stage 11/12 gates in `IMPLEMENTATION_PLAN.md`.

Replace authenticator-app TOTP with SMS OTP (via the existing notify.lk gateway),
add a Settings toggle to enable/disable 2FA, and allow the owner to change the
enrolled mobile number. When 2FA is disabled, login is email + password only.

**Approved deviation** from SECURITY_GUIDELINES.md ("mandatory TOTP — no bypass
path"): record in ARCHITECTURE.md §8. Accepted trade-offs: SMS is weaker than
app TOTP (SIM swap); disabling 2FA reduces login to a single factor. Mitigations
below ensure OTP can never be skipped *while 2FA is on*, and that disabling 2FA
or changing the number is itself authenticated, OTP-confirmed, and audited.

---

## 1. Threat model & invariants (the "no bypass" rules)

1. When `twofa_enabled = true`, **no code path issues access/refresh tokens
   without a fresh, verified OTP**. The only token the password step returns is
   a 5-min `otp_pending` JWT that cannot call any API route.
2. OTP codes are **random (secrets.randbelow), 6 digits, single-use, hashed at
   rest** (HMAC-SHA256 with MASTER_KEY-derived key), expire in 5 minutes,
   max **5 verify attempts** per challenge, then the challenge is dead.
3. The `otp_pending` token is **bound to one challenge row** (`challenge_id`
   claim). Replaying an old token or an already-consumed challenge fails.
4. **Resend throttling**: 60 s cooldown per challenge, max 5 SMS per user per
   hour (prevents SMS-bombing and cost abuse). Counted via `security` events,
   same DB-backed pattern as the existing login lockout.
5. Existing login lockout (5 failures / 15 min) also counts failed OTP attempts.
6. **Guarded settings changes** (all require the current password re-entered):
   - Disable 2FA → also requires a valid OTP to the *current* phone.
   - Enable 2FA / change phone → OTP sent to the *new* phone must be verified
     before the change commits (proves the owner controls that number).
   - Phone change / 2FA disable → notification SMS to the *old* number +
     `security` event + revoke all other sessions.
7. OTP values never appear in logs, events payloads, or API responses
   (extend the existing logging scrub test).
8. Generic error messages at the API edge (no "wrong code" vs "expired" leak
   beyond what UX needs); timing-safe hash comparison.
9. **Break-glass recovery**: server-side CLI only (`python -m app.cli reset-2fa
   --email …`) for when the phone is lost or notify.lk is down — requires shell
   access to the VPS, writes a `security` event. No web-based recovery path.
10. SMS OTP delivery is **not** fire-and-forget (unlike alerts): the login flow
    surfaces "could not send code — retry" on gateway failure and logs it.

## 2. Database (one Alembic migration)

- `users`: drop `totp_secret_encrypted`, `totp_enabled`;
  add `phone_encrypted TEXT NULL` (AES-GCM, same crypto helper),
  `twofa_enabled BOOLEAN NOT NULL DEFAULT false`.
- New table `otp_challenges`:
  `id PK · user_id FK · purpose TEXT ('login'|'enable_2fa'|'disable_2fa'|'change_phone')
  · code_hash TEXT · phone_encrypted TEXT (target number for this challenge)
  · attempts INT DEFAULT 0 · max_attempts INT DEFAULT 5
  · expires_at timestamptz · consumed_at timestamptz NULL
  · last_sent_at timestamptz · send_count INT DEFAULT 1 · created_at timestamptz`.
  Index on `(user_id, purpose, created_at)`. Periodic cleanup of expired rows
  piggybacks on an existing scheduler tick.
- Migration is destructive for the TOTP secret but preserves the prior enabled
  state. An enrolled owner fails closed (`twofa_enabled=true`, phone absent)
  until the inactive stack is re-enrolled with `app.cli set-phone`; traffic is
  promoted only after a real SMS login. Downgrade refuses while SMS 2FA is
  enabled because it cannot safely reconstruct the former TOTP secret.

## 3. Backend

### 3.1 `app/core/security.py`
- Remove pyotp + TOTP helpers (and the dependency).
- Add `generate_otp() -> str`, `hash_otp(code) -> str`, `verify_otp_hash(code,
  hash) -> bool` (HMAC-SHA256, `hmac.compare_digest`).
- `TokenPurpose`: `"totp_pending"` → `"otp_pending"`.

### 3.2 New `app/services/otp.py`
- `create_challenge(session, user, purpose, phone) -> Challenge` — enforces the
  per-hour send cap, generates + hashes code, persists row.
- `send_challenge(session, challenge)` — formats "CryptoPilot verification code:
  NNNNNN (valid 5 min)" and sends via `NotifyLkGateway` using the stored
  notify.lk credentials; returns ok/fail to the caller; writes an `events` row
  (status only, never the code).
- `resend(session, challenge)` — 60 s cooldown, bumps `send_count`.
- `verify(session, challenge_id, code) -> user_id` — attempts++, expiry check,
  timing-safe compare, marks `consumed_at`. Typed errors: `OtpExpired`,
  `OtpInvalid`, `OtpLocked`.

### 3.3 `app/services/auth.py`
- `authenticate_password` → returns either
  `("tokens", access, refresh)` when `twofa_enabled` is false, or
  `("otp", otp_pending_token)` after creating+sending a login challenge.
- `verify_totp_and_issue` → `verify_otp_and_issue(session, challenge_id, code)`;
  failed OTP still writes `login_fail:{email}` events (feeds lockout).
- New: `enable_twofa`, `disable_twofa`, `change_phone` orchestrations per the
  invariants in §1 (password recheck → challenge → verify → commit → notify old
  number → revoke other sessions → security event).

### 3.4 API (`app/api/auth.py`, `app/api/settings_api.py`, schemas)
- `POST /api/auth/login` → `LoginResponse { mode: "tokens"|"otp", …,
  phone_hint }` (masked, e.g. `···· 1234`).
- `POST /api/auth/otp/verify` (replaces `/auth/totp`) — bearer `otp_pending`.
- `POST /api/auth/otp/resend` — bearer `otp_pending`, 429 on cooldown/cap.
- Settings (all under current-session auth):
  - `GET  /api/settings/security` → `{ twofa_enabled, phone_hint }`
  - `POST /api/settings/security/2fa/start` — body: `{ password, action:
    "enable"|"disable"|"change_phone", new_phone? }` → sends OTP, returns
    `challenge_id`.
  - `POST /api/settings/security/2fa/confirm` — body: `{ challenge_id, code }`
    → commits the change.
- Phone format validated at the edge (`^94\d{9}$` — notify.lk format, matches
  the existing alerts phone convention).

### 3.5 CLI (`app/cli.py`)
- `create-owner`: replace `--totp-secret` with `--phone` (optional; without it
  the owner is created with 2FA off and enables it in Settings).
- New `reset-2fa --email` (break-glass: sets `twofa_enabled=false`, clears
  phone, security event) and `set-phone --email --phone`.

## 4. Frontend

- `api/client.ts`: new response shapes + endpoints; remove `verifyTotp`.
- `auth/Login.tsx`: on `mode:"tokens"` go straight in; on `mode:"otp"` route to
  the OTP screen.
- `auth/Totp.tsx` → `auth/Otp.tsx`: same card UI, SMS wording ("We sent a code
  to ···· 1234"), 6-digit input, **Resend code** button with 60 s countdown,
  distinct messages for expired vs invalid vs locked (as far as the API allows).
- `views/Settings.tsx`: new `SecurityCard` (pattern-matched to existing cards):
  - 2FA toggle (uses existing `toggle` + `ConfirmModal` patterns; danger tone
    when disabling, body text explains password-only login).
  - Phone row with masked hint + "Change number" flow.
  - Both flows: password prompt → code entry modal → success/error inline-msg.
- Keep prototype look & a11y patterns (`role="switch"`, `data-testid`s).

## 5. Tests & QA gate

- **Unit**: otp service (generate/hash/verify, expiry, attempts, cooldown, send
  cap), security.py helpers, logging scrub includes OTP-shaped payloads.
- **Integration** (extend `test_auth.py`, `test_hardening.py`):
  - 2FA on: password-only never yields tokens; `otp_pending` token rejected on
    every API route; consumed/expired/locked challenges; token↔challenge
    binding; resend cooldown 429; per-hour cap; lockout counts OTP failures.
  - 2FA off: login returns tokens directly; OTP endpoints return 4xx.
  - Settings flows: wrong password fails; disable requires OTP; phone change
    OTP goes to the new number; old number notified; other sessions revoked;
    all security events written.
  - Gateway failure at login → clean error, no token issued.
- **Playwright**: rewrite `qa/e2e/stage-01.auth.spec.ts` OTP steps (FakeSmsGateway
  exposes the code in test mode only), extend `stage-09.settings.spec.ts` with
  the SecurityCard flows. Full regression must stay green.
- Docs: update SECURITY_GUIDELINES.md, ARCHITECTURE.md §8 deviation entry,
  RUNBOOK.md (break-glass procedure), CREDENTIALS.md if needed.

## 6. Sequencing

1. Migration + models + core security helpers (remove pyotp).
2. OTP service + unit tests.
3. Auth service/API rewiring + integration tests.
4. Settings endpoints + tests.
5. CLI changes.
6. Frontend (Login/Otp/SecurityCard) + Playwright.
7. Docs + full regression + stage-gate report.

**Open items for the owner**
- notify.lk must be configured *before* enabling 2FA (the enable flow verifies
  this and refuses otherwise) — login OTP depends on it.
- Decide whether the login-OTP phone starts as a copy of the alerts phone or is
  always entered fresh in the enable flow (plan assumes: entered fresh).
