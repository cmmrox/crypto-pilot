# Experiment Lab implementation and QA checkpoint

Branch: `charithm/feature/experiment-lab`.
Checkpoint: 2026-09-06, local QA only. **Implementation remains in progress; not a
production release or a claim of a profitable optimized strategy.**

## Implemented and exercised

- Separate Lab API/replay worker with SQLite-owned jobs, leases, fencing,
  idempotency, cancel and review-only recovery.
- App-owned Codex advisor, strict structured decisions, parameter bounds/pins,
  bounded context and conservative eligibility. No trading lifespan in advisor.
- Shared v6 runtime with immutable production wrapper; existing research untouched.
- Single-screen study/baseline/manual/advised/reproduction history, monthly metrics,
  learned skill and non-activating candidate export.
- Binance public candles/funding, actual trade archive ingestion with checksum,
  sequence and OHLC guards; no synthetic market data represented as Binance data.
- Decision telemetry queued in the existing transaction and mirrored to logs;
  owner-only cursor export explicitly labels committed-event coverage.
- Separate owner/runner/advisor credentials; owner BFF cannot proxy worker jobs.
- Frozen runtime/evaluator identities and linked immutable context/output evidence.
- Cross-study lessons retain comparison scope; baseline/best ancestors survive
  recent-history truncation. Exact repeats are not independent replication.

## Test environment and accounts

PostgreSQL runs in the disposable `cryptopilot-lab-qa-postgres` local container.
Current database: `cryptopilot_lab_e2e`; older `cryptopilot_lab_qa` was preserved.
Current QA owner: `qa-owner@example.com`, provisioned by the guarded fixture.
Earlier disposable owner records remain; none is a production account. SMS is a
test-only gateway. No exchange keys were provisioned. The fixture advisor is
labeled synthetic and is not evidence of real model reasoning quality.

The backend binds 127.0.0.1:8000, Lab API 127.0.0.1:8010, and Vite 127.0.0.1:5173.
No production deployment, bot start or live-order action was performed.

## Evidence so far

| Check | Observed result |
|---|---|
| Backend full suite, including parity | Latest rerun: 250 passed, 3 skipped |
| Lab + legacy backtesting suite | 44 passed |
| Frontend unit tests | 7 passed |
| Frontend lint/typecheck/build | Passed after equity-curve implementation |
| Backend Ruff, strict mypy, import-linter | Passed; 89 source files, both existing boundaries kept |
| Full desktop/mobile Playwright, provisioned fixtures | 121 passed, 21 skipped |
| Dedicated QA-owner full-suite rerun | 121 passed, 21 skipped (3.6 minutes) |
| Final Lab desktop/mobile replay + equity-curve acceptance | 2 passed (30.4 seconds) |
| Standalone Lab with its own locked dependencies, Python 3.11 | 26 passed |
| App-image build with shared runtime wheel | Passed locally |
| Lab-image build | Current build passed after authorized Docker login |
| Disposable current-image acceptance | Passed scoped auth, actual-data replay, idempotency, restart persistence, exact reproduction and non-root isolation |
| Compose overlay config with test-only placeholders | Passed |
| Real Codex structured REVIEW capability | Passed schema and current-evidence citation after prompt correction |

The first full Playwright attempt exposed absent stage 2/6/7 fixture data and a
Vite cache-header mismatch. The existing guarded E2E seed and local no-store
configuration corrected these. A separate attempt failed when Vite stopped during
configuration reload; it was restarted before the green complete run. These failed
attempts are not reported as passes.

After the real-advisor correction, backend/parity was rerun (250 passed, 3 skipped),
Lab/backtesting (44 passed), frontend unit (7 passed), frontend lint/build and backend
Ruff/mypy/import boundaries passed. Browser's final four-run summary showed no captured
console errors. The full 121-pass Playwright evidence predates that prompt-only change;
it was not rerun against the isolated real-model study, to avoid fixture contamination.

Reusable bounded acceptance commands (repository-root cwd):

```sh
backend/.venv/bin/python qa/fixtures/lab_container_smoke.py PATH_TO_PUBLIC_DATASET_JSON
backend/.venv/bin/python qa/fixtures/lab_real_advisor.py PATH_TO_PUBLIC_DATASET_JSON --codex-home PATH_TO_AUTHENTICATED_CODEX_HOME --cycles 3
```

The real-advisor command creates a new isolated evidence directory each invocation;
it does not resume or overwrite previous studies. The container harness removes only
its explicitly generated disposable resources. Never supply an exchange credential.

The 21 skipped cases include credential-gated DEMO order/lifecycle and real SMS
checks, plus explicitly desktop-only mutations. They are not certified by local
mocked tests. Frozen research emits its existing pandas timezone warning; the Lab
test client emits a dependency deprecation warning.

An independent install initially selected Python 3.14, which crashed in pandas
date-range generation. The Lab now explicitly targets Python 3.11 (matching its
Docker image); the clean locked-environment run passed all 26 tests. The final
image rebuild initially could not obtain Docker Hub authorization. The owner's
authorized Docker login subsequently succeeded and both images built. The disposable
container harness exposed and corrected test-setup assumptions about internal-network
port publication, public artifact ownership and ephemeral ports after restart. Its
final run passed and removed only its UUID-named containers, volume and network.
This smoke test uses a dedicated bridge and loopback publication, not an egress-denied
network. Network-hardening and resource-failure drills remain separate gates.

## Real-advisor learning acceptance, 2026-09-06

Four completed runs used the application-owned `CodexAdvisor` (`gpt-5.5`) with existing
Codex login; no new login or API key was required. Dataset, 4h timeframe, initial
capital (100 USDT), dates (2023-09-01 to 2026-09-01 exclusive) and evaluator were fixed.
These are actual Binance **candle-screening** results, not verified tick execution.
All monetary results include modeled fees and funding; missing funding marks remain
explicit candle-price proxies. No liquidation/liquidity certification follows.

| Iteration | Net profit USDT | Ending equity | Max drawdown | Worst month | Profitable months | Profit factor | Trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 baseline | 659.56 | 759.56 | -46.93% | -10.79% | 38.89% | 1.3976 | 111 |
| 2 lower exposure | 343.38 | 443.38 | -37.17% | -10.13% | 41.67% | 1.4881 | 115 |
| 3 tighter exits | 104.24 | 204.24 | -31.83% | -8.55% | 36.11% | 1.2186 | 125 |
| 4 relax trailing exit | 294.16 | 394.16 | -31.32% | -9.48% | 41.67% | 1.3982 | 125 |

Iteration 2 changed risk_pct 15→10, leverage_cap 6→4 and long_month_cap .04→.03.
Iteration 3 changed stop_atr 2.5→2, trail_atr 4→3 and tp1_frac .4→.55.
Iteration 4 changed only trail_atr 3→4. The third hypothesis worsened profit quality;
the fourth recovered some profit and slightly improved drawdown but worsened the
worst month. **No run meets the user's profit-and-monthly-loss objective or qualifies
for live use.** Highest profit remains the baseline; latest does not mean best.

The first three runs used production ASGI handlers with isolated SQLite/artifacts
and the real provider, driven by `qa/fixtures/lab_real_advisor.py`. The fourth was
started in Browser using `qa-owner@example.com`, traversing the BFF, private HTTP
Lab API, separate replay worker and separate app-owned real advisor. Browser showed
history, hypotheses, monthly metrics and versioned learned skill. Four immutable
lesson revisions were retained; later decisions cited earlier actual iteration IDs.
No synthetic advisor lessons entered this store. This verifies evidence retrieval
and persistence, not improvement of the model's weights or general trading ability.

Real QA exposed an advisor evaluation flaw: it used the deliberately false
`suitable_for_live` flag as a parameter-hypothesis falsification test. The prompt now
separates comparative research criteria from deployment gates. The fourth review
correctly reported partial research improvement with deployment still blocked.
A regression test checks this instruction and prevents exchange-secret environment
inheritance. Provider structured output and restricted execution follow the official
[Codex non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

Evidence remains under `.lab-data/real-advisor/a8ff65fe2a2446519a6cba55503dd27a`.
Study: `c0ca15f961f14da6aa929487318d7f45`; iteration IDs, in order:
`9f0f4931e17440109ff0ae6362fde847`, `7f5948050cec4da6877810eeab6a07e4`,
`f1af8b82bc574b688c1508b6b0825b00`, `b48a6388117a4151b92cc366e2cd895c`.
QA workers were stopped after the requested cycles; no queued jobs remained.
The local UI/API remain available for inspection. No production bot or credentials
were changed, and no live orders were submitted.

Browser verification with `qa-owner@example.com` created and completed a new
three-year baseline from the UI. Iteration `5af729a649d54ca1903bcfa59488ce4e` shows
initial capital 100 USDT, ending equity 759.56 USDT, net profit 659.56 USDT,
111 closed trades, drawdown -46.93%, worst complete month -10.79%, and 38.89%
profitable months. The screen correctly reports no verified live candidate.
This is candle screening with 78 funding mark-price proxies and a fixture advisor,
not an optimized or trade-verified strategy. No live performance claim follows.
The Browser walkthrough also opened the immutable equity curve and checked the
monthly loss display, fees/funding, completed status and conservative readiness
reasons. The QA Lab is left running locally for continued inspection.

## Actual-data findings

The downloaded Binance 4h dataset covers 2023-09-01 through 2026-09-01 (exclusive),
with warmup and funding. Its ID is
`7d806927e478194e1fd2962933775b5bf3d26e5612c2ae4d03c784c1cd23af20`.

For 2026-08-01 00:00–04:00 UTC, the checksum-verified aggregate archive supplied
57,678 records. Its first price was 62859.8; the separately downloaded Binance
candle opens at 62859.9. The raw-trade daily archive
`ca0c8c028e5911e26380f6ae78dd730ffce1fcb1fd7d4e4e6b586afb8421cbaa`
contained a jump from trade ID 7945225108 to 7945225110. Strict verification rejects
this rather than synthesizing the missing trade or relaxing consistency.

Binance funding timestamps contain mixed whole-second and millisecond ISO strings;
the parser now accepts ISO8601 explicitly, with a regression test. Blank funding
mark prices are explicitly counted in candle screening and block exact trade
verification where needed. This is real-data validation evidence, **not** a passed
three-year tick replay or a finding that the live bot missed the September signal.

## Outstanding delivery/release gates

### Owner-requested batch stop and VPS comparison — 2026-09-06

Owner stopped the 50-additional-iteration request before completion. There are 26
completed iterations (the original four plus 22 additional), three failed SELECT
attempts and one replay whose REVIEW failed at the Codex rate limit. The local
experiment runner was stopped; no jobs remain pending. No live service was stopped.

Read-only VPS verification: clean source at a28b567; backend healthy; application
settings LIVE / trend_rider_v6_4h; active bot run 12 uses release 6.0 / 4h. The running
container's manifest and engine confirm the baseline settings: risk 15%, leverage
cap 6, long/short monthly breakers .04/.04, stop ATR 2.5, TP1 fraction .4 and trail
ATR 4. App database reports three LIVE closed trades during its rolling 30-day
window, gross realized PnL -25.97810000, fees 2.43798074 and funding -0.15466192.
It reports no open trades. This is application DB evidence, not fresh signed
Binance position/order reconciliation or a full runtime parity proof.

Among completed studies, #25 is the higher-return/lower-drawdown research shortlist
candidate: net profit 436.97, ending equity 536.97 from 100 USDT; drawdown -26.58%,
worst month -8.21%, profitable months 47.22%, doubled-cost profit 336.96. #27
repeats it exactly. Compared with the baseline it sacrifices profit (659.56) for
lower drawdown (baseline -46.93%); it does not dominate baseline on both metrics.
#10 has the lowest observed drawdown (-20.36%), profit 157.07, worst month -6.44%.
No observed candidate clears all research risk/monthly gates, and none is certified
for live activation. #25 should be prioritized for independent validation, not
automatically deployed. #10 is the lower-drawdown alternative for that validation.

The batch exposed and tested advisor context deduplication, structured text-length
limits, safe failure categories, and valid-evidence enum constraints. Five focused
advisor tests and advisor mypy/Ruff passed after these changes; these checks are not
a replacement for the outstanding full release regression gates below.

1. Complete formal walk-forward/untouched holdout evaluation, per-block trade gates,
   trial-exposure policy and liquidation/liquidity survival modeling. Current
   eligibility deliberately cannot certify a live candidate.
2. Resolve/independently verify archive gaps and funding-mark coverage before a
   full-period trade-level result is described as verified. Never fabricate data.
3. Finish generic multi-strategy registration/fixture coverage, richer evidence
   adjudication and rollback, and the reviewed candidate compatibility pipeline.
4. Complete database strict-schema migrations, backup/restore and disk-full/crash
   drills, resource tests and service-network hardening.
5. Finish dataset-preparation UX, history paging, production
   observation-to-Lab import and order/fill reconciliation evidence.
6. Final clean-code review and full resource/failure-drill coverage. Current image
   builds and disposable-container acceptance now pass; they do not substitute for
   the remaining resource/drill checks. Rebuild the app image for the subsequent
   advisor prompt correction before release. No commit/merge/deployment yet.

These remain open implementation work, not permissions to operate the live bot.

## Regression follow-up — 2026-09-07

See [the cross-application release regression report](RELEASE-REGRESSION-2026-09-07.md).
History paging, bounded context, SQLite index migrations, verified online backup/
restore, disk-full/artifact cleanup, lease/cancellation audit closure and local code
review are now implemented and tested. Earlier open-gate wording above is historical
for those specific items. Research qualification, unfinished product capabilities
and target-production operational gates remain open as listed in the new report.
