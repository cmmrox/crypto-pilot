# Stage 0 — Foundations & Walking Skeleton — Report

**Status:** ✅ COMPLETE — QA gate passed. **Date:** 2026-07-18.

## Scope shipped

A running Docker Compose stack (postgres · backend · frontend · caddy) with a real,
empty application skeleton that every later stage plugs into.

- **Backend** (`backend/`): FastAPI app factory, `/health` (DB + version), pydantic
  settings (env-driven, placeholder-secret rejection), structlog JSON logging with a
  sensitive-key scrubber, AES-GCM secret crypto, SQLAlchemy 2.0 models for the full
  13-table schema (`DATABASE_ARCHITECTURE.md`), Alembic wired with an initial
  migration (13 tables + 8 indexes).
- **Frontend** (`frontend/`): Vite + React 19 + TypeScript scaffold, walking-skeleton
  page that reaches `/health` through Caddy. ESLint + Prettier + strict tsconfig.
- **Deploy** (`deploy/`): `docker-compose.yml`, `Caddyfile` (reverse proxy + security
  headers), `.env.example`.
- **QA** (`qa/`): Playwright project (desktop + mobile projects), `stage-00.smoke.spec.ts`.
- **CI** (`.github/workflows/ci.yml`): backend (ruff → mypy → import-linter →
  migrations up/down → pytest+cov), frontend (audit → lint → build), gitleaks, E2E.
- **Tooling:** ruff, mypy strict, import-linter boundary contracts, gitleaks config.

## Test run summary

| Gate | Result |
|---|---|
| ruff (lint+format) | ✅ clean |
| mypy --strict | ✅ no issues, 19 files |
| import-linter | ✅ 2 contracts kept (strategy purity, news isolation) |
| Alembic up → down → up | ✅ reversible, **zero autogenerate drift** |
| pytest (unit + integration) | ✅ 15 passed, **93% coverage** |
| frontend audit | ✅ 0 vulnerabilities |
| frontend lint + build | ✅ clean |
| Playwright `stage-00.smoke` | ✅ 12 passed (6 cases × desktop + mobile) |
| Full stack via Caddy | ✅ /health ok, SPA served, migrations auto-applied, 14 DB tables |

QA-0 cases covered: health/DB, SPA served, live health render, security header,
**no secrets exposed to client**, SPA route fallback.

## Bugs found & fixed during the stage

| # | Sev | Issue | Fix |
|---|---|---|---|
| 1 | Major | `Money` annotated type passed as a `mapped_column` argument → SQLAlchemy `ArgumentError` | Standardized on `Mapped[Decimal]` + registry `type_annotation_map` (Decimal→Numeric(20,8)) |
| 2 | Minor | mypy strict: untyped `dict`/`list` JSONB columns, unused `type: ignore`, structlog processor signature | Typed as `dict[str, Any]`/`list[Any]`, fixed processor signature, removed stale ignores |
| 3 | Minor | ruff E501 on Alembic-generated migration | Per-file ignore for generated `migrations/versions/*` |
| 4 | Major | Frontend deps: 10 vulns (1 critical) in react-router/esbuild/eslint chain | Bumped react-router-dom, vite, vitest, eslint stack → **0 vulnerabilities** |
| 5 | Major | `npm ci` failed in Docker (cross-platform optional-dep mismatch in lock) | Clean-regenerated `package-lock.json` with all-platform optional deps |
| 6 | Minor | Caddy port 8080 held by a stale Docker proxy | Switched published port to 8090 |

No known open bugs.

## Loose-coupling / quality notes

- Module boundaries enforced by import-linter in CI, not convention: `strategies/`
  cannot import infra; `news/` cannot import trading. Contracts pass empty-but-real.
- All money is `Decimal`/`numeric(20,8)`; all timestamps `timestamptz`. Verified in
  the migration DDL.
- Secrets: AES-GCM module + log scrubber + gitleaks; verified no secret material in
  container logs or client responses.

## Docs updated

None required (docs authored pre-Stage-0 remain accurate). `deploy/docker-compose.yml`
port note reflects 8090.

## Sign-off

Stage 0 meets its exit criteria (compose stack + CI defined + skeleton deployed
locally, all gates green). Proceeding to Stage 1 (Authentication & app shell), which
also needs no external keys.
