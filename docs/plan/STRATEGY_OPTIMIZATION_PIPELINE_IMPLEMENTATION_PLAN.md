# CryptoPilot Experiment Lab — implementation plan, revision 2

Date: 2026-09-05
Status: proposed implementation; owner review pending.
Scope: one-screen, manually started, LLM-guided strategy experiments.
Supersedes the 2026-09-04 plan and its multi-step recommendation workflow.

## 1. Purpose and product contract

The owner wants to improve an existing trading strategy through recorded experiments.
The useful outcome is a better-supported candidate and reusable knowledge about why
changes succeeded or failed. The product must make this process simple:

1. Select a strategy and a saved experiment configuration.
2. Optionally edit initial parameters or pin values the agent must preserve.
3. Click **Run next iteration**.
4. At that moment, the LLM reads previous inputs, results, failed experiments, and
   the strategy's current learning skill; it selects the next parameters.
5. Deterministic code validates and runs that one candidate against Binance history.
6. The LLM evaluates the measured result and updates the strategy's learning record.
7. The screen shows the result, comparison, and lesson. Another iteration requires
   another owner click.

This is parameter optimization with an LLM using external memory. It does not train
the LLM's model weights. The LLM proposes a testable hypothesis; the backtest measures
its outcome. An iteration can lose money or disprove a hypothesis. Preserving that
failure is part of learning.

### 1.1 Required behavior

| Requirement | Implementation contract |
|---|---|
| Simple interface | One route, summary strip, run controls, iteration list, expandable detail |
| Edit existing strategy | Create a candidate from a pinned release; edit candidate inputs |
| LLM chooses at start | Default Run command queues advice before executing the candidate |
| Manual iteration control | One owner Run command permits one candidate cycle, then stops |
| Past inputs and outputs | Immutable run specification, result bundle, comparison, and lesson |
| Persistent skill | Stable methodology plus versioned strategy playbook and evidence |
| Agent can ask for more data | Bounded requests for computed evidence summaries |
| Real Binance data | Official USD-M trade archives, candles, funding and labeled account fills |
| Compare timeframes | Separate studies under one strategy workspace, comparable-period summaries |
| More profit with lower losses | Profit ranking subject to explicit monthly and drawdown constraints |
| Separate microservice | Lab owns workflows/storage; main app owns LLM/provider configuration |
| Easy CryptoPilot integration | Shared versioned runtime contract and exportable candidate manifest |
| Maintainable code | Tested parameterization, explicit ownership, bounded refactoring |

The existing production release remains immutable. A candidate has its own identity,
parameters, risk specification, and evidence. Importing and activating it in the live
bot is a distinct release operation.

### 1.2 What the previous plan missed

| Review finding | Why it matters | Correction in revision 2 |
|---|---|---|
| Prepare → apply → confirm became the main path | Conflicted with “agent decides when I start the next iteration” | Single default Run command starts advice, validation, replay, evaluation |
| Both services appeared to coordinate the run | Restart recovery and completion ownership were unclear | Lab is the only workflow owner; main-app worker fulfills durable advice requests |
| Parameter editor assumed the existing plugin was mutable | Plugin behavior reads engine constants, not edited metadata | Extract parameterized pure runtime and prove every exposed parameter is consumed |
| Lab inherited backend internals | Microservice would still need the trading application at runtime | Install a small shared runtime wheel in both applications |
| Every iteration needed excessive UI columns | Recreated the complexity the owner rejected | Eight primary columns; remaining evidence expands within the row |
| Repeated validation was labeled out-of-sample | The agent can overfit information reused in later iterations | Track data exposure across studies and knowledge; distinguish development from untouched evaluation |
| Repeating a fold “verified” a lesson | Repetition on the same data is not independent support | Evidence groups, contradictions, and applicability qualify lessons |
| Highest profit was replaced by vague risk-adjusted score | Did not clearly answer the owner's profit question | Show highest net profit and recommended feasible result separately |
| Identical parameters were always rejected | Prevented requested second-time verification | Explicit reproduce mode with fresh execution and result comparison |
| SQLite money representation and artifact commits were unspecified | Float conversion and partial writes could corrupt comparisons | Canonical decimal text, immutable files, atomic publication, short transactions |
| Production telemetry was only an arrow in the diagram | Missed-signal investigations need actual decision/order lineage | Defined observation schema, incremental export, coverage, and delivery behavior |
| OpenAI API schema support was assumed for existing provider | Current app uses a device-authenticated CLI provider | Provider capability test precedes integration; no assumed API/auth migration |

## 2. Current code evidence and required engineering work

This review inspected the current checkout. It did not run a backtest, verify VPS
state, or certify historical test reports as current.

- `backend/app/strategies/plugins/trend_rider_v6_4h.py` exposes a `params` dictionary,
  but `on_candle()` reads `engine.TRAIL_ATR`, `engine.SLEEVE_DEPTH_ATR`, and other
  constants. Editing that dictionary is insufficient.
- `backend/app/strategies/engine.py` fixes indicator lengths, ATR period, and
  `BARS_PER_YEAR=2190`. Timeframe changes require explicit calculations.
- `experiments/backtesting/src/trend_rider_lab/replay.py` selects the default plugin,
  inherits strategy-specific replay behavior, enforces continuous 4h data and
  200 warmup bars, and still uses engine constants in execution simulation.
- Its first monthly return uses the first recorded equity instead of initial capital;
  its drawdown starts from the first recorded equity. Add a start-boundary equity
  observation so first-bar losses are included. Confirm with a regression fixture.
- `reporting.py` aggregates costs from closed trades while ending equity can include
  an open position. Add a complete cash/fill/funding ledger reconciliation.
- `backend/app/news/provider.py` and `codex_auth.py` own the existing LLM integration.
  Its permissive news-text parser is unsuitable for executable parameter proposals.
- Main backend serves APIs and starts background services in its lifespan.
  Research inference and replay require separately bounded processes.
- Frontend already has React, TanStack Query, Recharts, and the approved dark/amber
  shell. Reuse them.
- Current production catalog accepts the approved 4h policy. A lab 1h/30m result
  cannot be labeled deployable until runtime support is separately tested.
- Existing uncommitted backtesting changes belong to the working baseline. Capture
  source hashes and characterization results before refactoring; preserve them.

These findings require a focused refactor of strategy parameter consumption, replay
composition, exact metric accounting, and provider boundaries. They do not justify
rewriting unrelated application modules.

## 3. Architecture and ownership

### 3.1 Runtime topology

~~~text
Owner → CryptoPilot React: /experiment-lab
              │ authenticated HTTP
              ▼
       CryptoPilot backend
       - owner authorization and settings
       - thin ExperimentLabClient
       - sanitized live-evidence exporter
              │ command / query
              ▼
       Experiment Lab service                         Main-app advisor worker
       experiments/experiment_lab/                    backend/app/experiment_advisor/
       - API + workflow coordinator     ← claim work ─ - LLM policy and provider
       - parameter/result policy        ─ context ──→ - provider authentication
       - all durable workflow state     ← result ──── - bounded evidence requests
       - one replay subprocess                        - no independent job database
              │
       SQLite metadata + immutable artifacts
              │
       Binance USD-M public archives / market data

Both lab runner and production plugin depend on a pinned strategy-runtime package.
Neither the advisor nor lab has a route to order placement.
~~~

The advisor worker is built from the main application's codebase and configured
through the main application's LLM settings. It runs as a separate process/container
role so inference cannot exhaust the trading API's resources. This satisfies “LLM
defined in the main application” while leaving experiment ownership in the lab.

### 3.2 Ownership table

| Concern | Sole authority |
|---|---|
| Owner identity, provider login/model settings | Main application |
| Strategy release used by active bot | Production registry |
| Candidate parameter schema and pure strategy behavior | Versioned shared runtime |
| Study, iteration, workflow, canonical parameter validation | Experiment Lab |
| Numerical results, comparison, risk gates, champion selection | Experiment Lab deterministic code |
| Advice prompt, bounded reasoning, response parsing | Main-app advisor worker |
| Learning observations, versions, retrieval eligibility | Experiment Lab |
| Raw market files, run artifacts, backups | Experiment Lab |
| Actual account fills and live positions | Binance, recorded/reconciled by main app |
| Rendering and draft form state | Frontend |

No service reads another service's database or mutable runtime directory. Main app
uses the lab HTTP contract. Lab receives sanitized observation batches, not database
credentials. Shared libraries contain pure code and immutable definitions, not ORM
models or application services.

### 3.3 One durable workflow, no distributed guessing

The lab stores an iteration and its current work items. When advice is needed it
inserts an `advisor_task` in the same transaction as the state change.

The app-owned advisor worker claims this task by private API, receives a frozen
context manifest, calls the provider, and submits the structured response with a
lease token. The lab validates the response and advances its workflow.

The same mechanism handles result evaluation after replay. Nothing depends on the
browser polling, a long HTTP connection, or a best-effort callback. Restarting either
application leaves durable work available for recovery.

Start with one lab coordinator and one advisor consumer. A SQL-backed work table is
sufficient; Redis, Celery, Kafka, a vector database, and Optuna are not required.

## 4. One-screen product design

Use the existing CryptoPilot visual system. All values below are placeholders,
not claimed experiment results. The header shows completed candidate iterations;
baseline, failed attempts, reproductions and diagnostic runs have separate counts.

~~~text
EXPERIMENT LAB
Strategy [Trend Rider v6 ▼]    Study [BTCUSDT · 4h · 3 years ▼]

Completed: —   Highest profit: #— / — USDT   Recommended: #— / — USDT
Recommended: worst month —% · max drawdown —% · profitable months —/—
[ small equity sparkline for selected result ]

Period [start → end]   Timeframe [4h ▼]   Capital [— USDT]
[Edit parameters ▾]  [Learning notes ▾]          [Run next iteration]

Current iteration #—: Agent reviewing prior results…
Hypothesis / parameter change / progress / final lesson appears here.

#   Result       Net P&L / %   Trades   Period / TF   Changed inputs   Learning
—   Complete     — / —        —        — / 4h        —                —
—   Failed       unavailable  —        — / 4h        —                —

Expand an iteration:
  full input values and changes → measured outputs → comparison → lesson
  monthly table / equity / trades / evidence downloads on demand
~~~

### 4.1 Default and optional actions

- **Run next iteration:** owner authorizes one cycle within the displayed study
  limits. LLM chooses parameters at run time; valid output proceeds automatically.
  No second routine approval click is required for this historical experiment.
- **Edit parameters:** change the initial seed or pin specific values. Pinned values
  are immutable for that run; the LLM can change only allowed, unpinned keys.
- **Run exact inputs:** secondary action for an intentional manual experiment,
  explicitly labeled `MANUAL`. Never an automatic fallback from failed advice.
- **Reproduce:** rerun a historical immutable specification for verification.
- **Cancel:** cancels pending advice/run work for this cycle.
- **Retry analysis:** resumes failed learning without rerunning the backtest.
- **Validate finalist / Export candidate:** secondary actions in expanded detail.
- A running row shows actual stage, elapsed time and processed/total bars when known.
  Never invent a progress percentage or numerical ETA.

List columns stay limited to iteration ID, status, net P&L/return, trades, period/
timeframe, changed inputs, and learning summary. Drawdown, worst month, costs, model
details and all other requested outputs remain available in expanded detail.
Failures stay in the list; no-trade results show zero activity with an explanation.

Study selectors allow saved variants under a strategy. Changing period, capital,
timeframe, costs or risk objectives creates a new study revision with clear
comparability status. It never rewrites old rows.

Frontend feature boundary:

~~~text
frontend/src/features/experiment-lab/
  ExperimentLabPage.tsx
  components/    StrategySummary, RunControls, ParameterEditor,
                 IterationTable, IterationDetail, LearningNotes
  api/           typed requests and DTOs
  hooks/         query/polling and draft handling
~~~

Use a lightweight summary query and paginated history. Fetch detailed trades and
series only on expansion. Poll active work every four seconds, back off when idle,
and mark stale data. Browser refresh resumes the same server-owned cycle.
Support keyboard operation and 390px layout using collapsible rows and contained
table scrolling.

## 5. Strategy runtime and clean-code migration

### 5.1 Shared pure package

Create `packages/strategy_runtime/`, built as an independently versioned wheel.
Both backend and lab install the exact wheel hash recorded in their lock/build.

It owns:
- shared Candle, TradeState, Intent and immutable manifest types;
- immutable TrendRiderParameters and generic parameter-schema types;
- pure indicator/state/intent functions;
- pure sizing/quantity-filter arithmetic moved with behavior tests;
- supported strategy factories and timeframe requirements.

It has no API, ORM, credentials, clocks, file/network I/O or plugin auto-discovery
side effects. Production catalog remains in the backend. Existing public import
paths can re-export shared types during migration to preserve type identity.

Production v6 becomes an immutable wrapper passing its pinned defaults to the shared
core. Lab candidates invoke the same core with their own validated inputs. Keep the
frozen research tree and independent reference engine as comparison oracles.
Do not monkey-patch constants, mutate registry singleton objects, dynamically execute
LLM code, or maintain a second copied Trend Rider implementation.

### 5.2 Binding every editable parameter

Create a checked-in parameter-consumption map:

| Parameter family | Must affect |
|---|---|
| EMA/SMA/ATR lengths | Actual indicators, warmup and history requirements |
| stop_atr, tp1_r, trail_atr | Intent construction and corresponding management behavior |
| tp1_frac | Simulated partial fills and export-compatible execution policy |
| sleeve_depth_atr, weight, vol target/span | Short entry, exposure and resize calculation |
| risk percentage, leverage, breaker caps | Candidate risk specification passed to replay |
| timeframe | Aggregation, candle clock, annualization, indicator time horizon |

Parameter keys include type, unit, default, bounds, step, tunable flag, allowed-change
limit and consumer. A unit test changes each tunable key on a discriminating fixture
and proves that the intended computation changes. A runtime cannot expose an editor
for a value it ignores.

Keep numerical risk percentages and ratio units explicit: `risk_pct=15` is percent,
whereas a `monthly_loss_fraction=0.04` is a fraction. Reject ambiguous conversions.

### 5.3 Candidate interface

~~~text
ExperimentAdapter
  describe() -> StrategyDescriptor + ParameterSchema
  validate(parameters, timeframe) -> EffectiveCandidateSpec
  build(effective_spec) -> PureStrategy
  requirements(effective_spec) -> Warmup/Data/ExecutionRequirements

ReplayPort.run(
  candidate_spec, dataset_manifest, evaluation_protocol, cancellation
) -> ArtifactManifest
~~~

`EffectiveCandidateSpec` contains strategy logic parameters AND execution/risk policy.
Changing metadata without changing effective replay inputs is a test failure.

Lab 4h is implemented first; 1h and 30m are subsequent adapters of the same family,
with explicit bar-count versus elapsed-time parameter semantics. They get separate
study IDs and baseline runs. Production remains on its approved 4h release until
support for another interval is verified through its own release gates.

### 5.4 Bounded refactoring sequence

1. Capture golden outputs and current source hashes, including working changes.
2. Extract types/math with compatibility wrappers; require unchanged baseline intent,
   fill, position and breaker traces.
3. Parameterize one family at a time, prove baseline parity and parameter consumption.
4. Replace replay inheritance with composition: strategy, execution model, ledger,
   clock, funding schedule and metrics calculator.
5. Correct metric-accounting defects separately with a new metrics version and
   before/after fixture evidence. Historical reports retain their old version.
6. Remove temporary adapters only after CLI, app and lab callers are migrated.

Production math changes require the full parity gate. Unrelated refactors ship
separately when a concrete defect is found.

## 6. Iteration semantics and durable lifecycle

### 6.1 Identities

- Workspace: one strategy family and its studies.
- Study: fixed strategy source, dataset version, timeframe, capital, parameter space,
  execution assumptions and evaluation/objective policy.
- Iteration: one manually initiated candidate cycle; includes proposal and learning.
- Parent: parameter set from which the candidate differs. May be an earlier best
  candidate, not necessarily the last chronological iteration.
- Attempt: retry of the same frozen stage/specification after operational failure.
- Evaluation run: base, chronological fold, fixed stress, or finalist test under the
  candidate. Each is recorded; no hidden parameter search.
- Reproduction: separate verification record for a prior specification; excluded from
  independent-trial counts and knowledge-strength increments.

### 6.2 Default sequence

~~~text
Run next iteration
  → save command, owner intent and scope
  → ensure baseline for a new study
  → freeze evidence/knowledge snapshot
  → request LLM parameter choice
  → validate full effective candidate
  → freeze run specification
  → verify data and execute deterministic evaluations
  → publish results and update numerical rankings
  → request LLM result evaluation
  → validate lessons and publish playbook revision
  → completed; await another owner action
~~~

First use: **Run baseline** uses the selected seed unchanged, then asks the LLM to
analyze it and initializes learning. Future clicks use the default LLM choice.
The UI labels the baseline separately; it never invents prior experience.

If all values are pinned or no useful legal change exists, the agent returns
`NO_PROPOSAL` with a reason. No implicit duplicate replay.

Take the history/skill snapshot after preceding analysis finishes and at the moment
the new cycle starts. Pin its revision throughout advice and replay. New observations
arriving mid-run are eligible for the next cycle, not retroactively inserted into the
current recommendation.

### 6.3 State and recovery

Separate experiment state from learning state:

~~~text
QUEUED → CONTEXT → ADVISING → VALIDATING → RUNNING → RESULTS_READY → COMPLETED
                    │             │          │
                    └→ BLOCKED    └→ REJECTED └→ FAILED/CANCELLED

learning_status: PENDING → RUNNING → COMPLETE | FAILED
~~~

Results remain usable when learning fails. The row reads “Results ready · analysis
failed.” In default LLM mode, the next run waits for missing analysis to retry;
the owner may explicitly select Run exact inputs instead. Never substitute old
advice after a timeout.

A proposed stage can return an information request; the coordinator computes existing
evidence and returns it within the call budget. Requests for new candidate backtests
cannot execute as a summary request.

### 6.4 Reliability contract

- Run creation transaction assigns a unique iteration number and idempotency key.
  Same key/body returns the existing iteration; same key/different body is a conflict.
- One active cycle per study; one replay subprocess globally initially.
- Stage claim uses an atomic compare-and-set with lease expiry and fencing generation.
  Every completion must match the current generation and uncancelled state.
- Process heartbeats are progress signals. Expired generations cannot publish late
  results after a retry or cancellation.
- Delivery is at least once; accepted state transitions/results are idempotent.
  A provider call may repeat after a crash and incur cost; record attempts and bound
  retries. Do not claim exactly-once external inference.
- Once validated, a proposal is frozen. Retry a replay with those same parameters.
  A fresh proposal is a new iteration, not an invisible retry.
- Start with full replay restart from immutable inputs; do not promise mid-position
  resume until a complete checkpoint format is implemented and tested.
- Cancellation terminates the subprocess group, rejects late completion and preserves
  diagnostics. Numerical failure never becomes zero profit.
- Work continues after browser close. Main-app downtime pauses only needed inference;
  an already frozen replay can complete.
- No worker holds a database transaction across a provider, network or replay call.

## 7. LLM behavior, evidence and learning skill

### 7.1 Provider ownership

Create `backend/app/llm/` for provider transport/authentication and
`backend/app/experiment_advisor/` for experiment prompts, task consumer, context
rendering and strict response parsing. News remains a separate consumer with its own
fixed summarization policy. The lab owns numerical validation of proposals.

Keep the current provider behind an interface. Before extraction, verify the
installed provider's supported structured-output mechanism, timeout/cancellation,
authentication refresh and isolation. The existing permissive news fallback must
never turn malformed advice into a runnable parameter object. Do not assume API
features are available through the device-login CLI.

Provider/model settings are managed by the main application. The app-owned advisor
process receives only its provider auth and scoped lab token. It must not initialize
the main FastAPI lifespan, trading scheduler or production database connection.

### 7.2 Context assembled from evidence

The lab constructs a frozen evidence package containing:
- strategy explanation, parameter schema, current seed/pins and search limits;
- complete compact parameter/metric history for the study;
- latest completed iteration, baseline, recommended candidate and recent failures;
- exact monthly, side, exit-reason, cost and regime summaries selected by policy;
- versioned playbook plus relevant supporting AND contradicting observations;
- data/metric/execution versions, unavailable fields and exposure restrictions.

Large history is paginated/retrieved with a bounded index. Preserve the full history
in storage; select representative failures and near-neighbor candidates as well as
winners. Record exact retrieved IDs, omitted-record counts and truncation.
Do not send three years of raw trades to the LLM.

Allowed requests: comparison, monthly distribution, long/short contribution,
holding duration, MAE/MFE where available, drawdown episodes, costs, blocker reasons,
and known sensitivity results. The lab verifies IDs, scope, time access and row budget.
Missing evidence is `UNAVAILABLE`; the LLM cannot make it up.

### 7.3 Structured decisions and budgets

Propose response:
- action: PROPOSE / REQUEST_EVIDENCE / NO_PROPOSAL;
- selected parent and complete effective parameter set;
- precise parameter delta and hypothesis;
- evidence references and applicable lesson IDs;
- expected direction of measured effects, counter-evidence, and uncertainty;
- success/failure criteria to check after the run.

Evaluate response:
- expected versus measured effects with metric references;
- better/worse/insufficient-evidence explanation;
- failed assumptions and operational/data caveats;
- proposed scoped observations and playbook amendments.

Initial versioned budget: one proposal call, at most two extra evidence/repair calls,
one evaluation call plus one repair, one concurrent provider task, bounded context
and output, and a configured wall-time limit. Record tokens/cost when supplied by the
provider; otherwise show unavailable. Retries count against the budget.

Default maximum three unpinned parameter changes; one is preferred for clear
attribution. Manual edits, bounds, and run-specific budget are frozen before advice.
Validate finite values, exact keys, units, types, ranges, steps, cross-rules, parent,
pins, timeframe and historical exposure. A syntactically valid JSON response can
still fail semantic validation.

The LLM cannot change the evaluator, transaction costs, dataset, objective thresholds
or its own permissions to improve its score. These are study policy, not strategy
tuning parameters. Changing them requires a visible new study revision.

### 7.3.1 How a next parameter set is selected

1. Compare baseline, latest run and best feasible run under the same protocol.
2. Identify the largest measured weakness: for example a loss cluster, missed trends,
   excessive turnover, weak short contribution or execution sensitivity.
3. Retrieve the failed and successful attempts that already tested that weakness.
4. Choose an existing parent and one supported parameter family to explore; state
   the observation, proposed change and falsifiable expected effect separately.
5. Propose a bounded local change or revert a failed change. The agent may explore
   another allowed family when local results have stopped improving.
6. Compare the actual outcome with the pre-run criteria; persist improvements,
   regressions and uncertainty. A recommendation to repeat an already exhausted idea
   must explain what new evidence would make the test useful.

Track a configurable stagnation count, initially five completed candidates without a
new feasible best. After that, the agent recommends stopping or a specific new
hypothesis. The owner can start another cycle, but the system never spends resources
on an unattended continuation. This is a bounded heuristic search; it cannot certify
the global maximum profit over an arbitrary parameter space.

### 7.4 A skill that actually evolves

Provide a strategy-specific **Learning Skill** assembled from three sources:

1. **Methodology policy:** reviewed instructions in the main app's code. Defines how
   to compare runs, request evidence and avoid unsupported conclusions.
2. **Evidence ledger:** append-only facts and hypotheses per iteration in lab storage.
3. **Learning playbook:** versioned Markdown/JSON compiled from eligible observations
   and validated LLM amendments. Loaded into each new advice task.

After each completed analysis, create a new skill revision, even if the conclusion is
“no additional supported lesson.” Save the exact old/new diff and evidence links.
This directly implements the requested evolving skill. Changes to learned content
are automated; changes to execution permissions or evaluation rules are code changes.

Observation fields:
`strategy_family, source_version, timeframe, scope, claim, parameter_delta,
metric_effects, support_ids, contradiction_ids, evidence_groups, first_seen,
last_reviewed, status, supersedes, exposure_tags`.

Statuses: OBSERVED, REPLICATED, DISPUTED, SUPERSEDED. Replication requires another
eligible evidence group, not merely a rerun or overlapping fold. “Replicated” means
supported within the recorded conditions, not a universal trading truth.

Deterministic checks establish that referenced results exist, numbers match, and
comparisons share a protocol. They cannot prove a free-form causal claim. Store
interpretations as hypotheses with limited confidence. If three parameters changed,
the lesson attributes the effect to that combination.

Retrieval includes applicable disputed evidence so the agent cannot keep repeating
a failed idea. Cross-strategy lessons retain their original scope and require
compatible evidence; human approval cannot turn a hypothesis into a proven fact.
LLM confidence labels describe its assessment, not calibrated success probabilities.

Store exact sanitized prompts/context, structured responses, policy version,
model identifier, runtime version and skill hash in protected artifacts. Hashes
alone do not make a request reproducible. Never put prompt bodies in stdout logs.
Replaying the frozen chosen parameters is deterministic; regenerating the same LLM
answer is not guaranteed.

### 7.5 Evaluate the advisor as a product component

Use fixed historical development tasks to compare:
- unchanged baseline;
- equal-budget simple random/local parameter selection;
- LLM selection without learned playbook;
- LLM selection with playbook.

Measure feasible-candidate rate, improvement against baseline, invalid/duplicate
proposals, evidence-reference errors, analysis quality and compute/provider cost.
Use multiple bounded trials where stochasticity matters; keep this evaluation outside
the final trading holdout. If accumulated “skill” adds no measurable value, revise
retrieval/policy rather than claiming automatic intelligence improvement.

## 8. Actual Binance data and realistic replay

### 8.1 Data contract

Use BTCUSDT **USD-M perpetual** as the initial market. Spot, DEMO price feeds, mark
prices and perpetual trade prices are separately identified.

Official Binance archives provide futures trades/aggregate trades and klines plus
checksums. Archives can later be corrected, so freeze downloaded bytes and hashes;
a changed archive creates a new dataset version. [Binance public data](https://github.com/binance/binance-public-data)

Two explicit execution modes:
- **CANDLE_REPLAY:** official candles/funding with a documented OHLC fill convention;
  useful for baseline compatibility and rapid screening.
- **TRADE_REPLAY:** actual Binance trade events drive simulated fills and intrabar
  order timing; required for final candidate verification in this feature.

Prepare official candle/funding data for the complete period. Download actual
trade/aggTrade partitions on demand, from possible entry through full open-position
lifetime, including stop/TP/resize/breaker events. Do not validate only windows around
exits already chosen by the candle model: different fills can change the whole path.
Cache missing partitions as the chronological replay progresses. Full-period archive
prefetch is available subject to measured disk budget.

All compared results must share the execution mode and cost model. Trade mode may
change returns. Show that as an execution-model comparison, not strategy improvement.
Actual market trades are not actual fills of our hypothetical historical orders.
The tape does not supply full order-book queue priority or historical market impact.

### 8.2 Storage and data quality

- Raw archives immutable; partition normalized Parquet by market/symbol/date/type.
- Use decimal/fixed-scale price/quantity fields, integer UTC event timestamps.
- Normalize timestamp units per source/schema; verify monotonic ordering, IDs,
  deduplication, OHLC/volume consistency and completeness.
- Aggregate closed timeframe bars in UTC and compare with official klines; report
  differences before scoring.
- Freeze funding schedules, available mark data and exchange filters.
  Current filters applied historically must be labeled an assumption.
- Historical mark/funding gaps and unavailable exchange filters remain visible.
  No silently invented historical bid/ask, fee tier or liquidation evidence.
- One immutable DatasetManifest contains raw/derived hashes, UTC boundaries, warmup,
  provider/schema versions, completeness and execution-model inputs.
- Large data remains on disk/object storage; SQLite stores metadata and references.

### 8.3 Replay event order

Define and test an explicit clock and tie-break order: scheduled funding, eligible
queued order activation, trade events/fills, position/risk updates, bar close,
strategy decision, then future eligible execution. Any source-specific same-timestamp
ambiguity uses a documented conservative rule and produces an ambiguity count.
A signal cannot fill on a trade already consumed to create that signal.

Model partial closes, gap-through stops, TP eligibility, volume participation caps,
quantity filters, fees, funding, resize and independent monthly breakers. Charge
each cost once: slippage changes execution prices; it must not also be deducted as
a second fictional fee. Preserve v6's stop-free short behavior.

If realistic maintenance margin/liquidation inputs are absent, report
`survivability=UNVERIFIED`, never “no liquidation proved.” Reject negative-equity
continuation and undefined CAGR explicitly.

## 9. Fair evaluation and monthly consistency

### 9.1 Development versus fresh evidence

Freeze the last 36 complete calendar months at study creation (for a September
2026 study: 2023-09-01 through 2026-09-01 exclusive) plus warmup. Exact dates are
owner-editable when creating a different study.

A starting template is months 1–12 for initial development, months 13–24 as six
chronological 2-month development-validation blocks, and months 25–36 reserved for
final evaluation where exposure provenance permits. Also report the continuous
months 1–24 replay. Each independent diagnostic block starts flat, warms indicators
from preceding data, and marks its ending position; do not concatenate its P&L as
though positions carried across blocks. Fixed candidate parameters are tested across
blocks; this alone is not a simulation of an adaptive live retraining system.

All results shown to the advisor become development information for later choices.
Repeated validation is useful for comparison but is not untouched out-of-sample
proof. [QuantConnect parameter guidance](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters)

Critical for this project: prior backtests and frozen research have already used
historical years. Do not relabel previously viewed dates as pristine just because a
new study was created. Track exposure across strategy lineage, all study revisions,
manual imports, knowledge and model context. Unknown provenance defaults to exposed.

Reserve a fresh final period only where provenance supports it. Otherwise use the
three-year history as development and collect prospective shadow evidence.
Opening a final evaluation is terminal for that selection attempt. Continuing to tune
after viewing it makes that period development globally; a new study name does not
reset exposure. Exclude final-period knowledge and live observations from earlier
historical tasks.

For evaluating the advisor's historical selection process, restrict all retrieved
evidence to each decision cutoff and disclose that model pretraining can include
historical information. Prospective results are the stronger test.

### 9.2 Objective policy

User goal: maximize net profit with stable months and limited losses.

Record a versioned risk policy when the study is created. Suggested initial research
limits, subject to baseline feasibility review:
- maximum equity drawdown: 20%;
- worst complete-month return: no worse than -5%;
- profitable complete months: at least 70%, with at least 12 evaluated months;
- at least 30 closed trades overall and five per comparison block;
- positive aggregate return after the declared stress costs;
- no invalid data/accounting result; execution/survivability limitations visible.

These are selection thresholds, not loss guarantees or validated recommended live
settings. If the existing aggressive strategy fails, show “No qualifying candidate.”
Do not relax limits automatically. Owner changes create a new policy revision and
re-rank all comparable results.

Display:
1. **Highest profit:** greatest net return in the comparable development evaluation,
   even if it fails risk limits.
2. **Recommended:** greatest net return among candidates meeting all declared
   eligibility gates. Break ties by smaller worst loss, lower drawdown, more
   profitable months, smaller cost and parameter change.

Show observed results and gate reasons instead of a mysterious combined score.
Timeframe comparisons use identical date coverage, capital, metric version and cost
assumptions with the necessary timeframe-specific execution model. Otherwise show
“Not directly comparable” and omit a shared winner.

### 9.3 Metric definitions

- Equity at time t = cash plus marked unrealized P&L, after booked fees/funding.
- Net P&L = ending marked equity minus initial capital, assuming no external flows.
- Include initial-capital observation before the first simulated event for drawdown
  and first-month return.
- Monthly return = month-end marked equity / prior boundary equity - 1.
  Label partial months separately; flat months count in denominator, not profitable.
- Closed trade P&L, remaining open P&L, all fill fees and funding reconcile to equity.
- Profit factor = sum of positive closed-trade net P&L divided by absolute sum of
  negative closed-trade net P&L; no-loss denominator is undefined, not zero or infinity.
  Report price-move gross profit/loss separately from net winners/losers.
- Common UTC daily return grid for Sharpe comparisons across timeframes; explicit
  annualization, zero-variance handling and metric version.
- CAGR uses elapsed time and positive capital/equity; invalid or too-short series
  return unavailable with reason.
- Full trade counts, long/short attribution, exposure, skipped signals, breaker trips,
  monthly losses, drawdown duration and cost breakdown are available in row detail.

Default stress evaluation uses a predeclared adverse cost scenario; additional
scenarios and parameter-neighborhood tests are visible verification work.
A neighborhood test that changes parameters is recorded as a separate diagnostic
candidate and counts toward the study's total search exposure and budget.

## 10. Production observations for future learning

Extend the application through an observation interface around existing orchestration
events. Pure strategies and order-placement classes do not write research tables.

Persist:
- decision ID, bot run, environment, source release/hash, interval and UTC candle
  open/close/evaluation times;
- received data age/completeness, feature snapshot, state and intent/no-intent;
- independent blocker result, reason code, and whether underlying conditions were
  actually evaluated or unavailable;
- order request/ack/fill IDs, requested and executed quantity/price;
- fees, funding, latency, rejection, partial fill and reconciliation differences;
- coverage and schema version.

Use these to answer: “Did the strategy signal? Was it blocked? Was an order sent?
Did Binance fill it?” A blocked signal is not automatically a bot defect.
An unseen counterfactual trade is never assigned invented real P&L.

Main app exposes a read-only, authenticated cursor export. An app-owned exporter
delivers sanitized batches to lab ingestion; lab deduplicates source IDs and persists
a high-water mark. No synchronous HTTP call from the candle/order path.
Build from existing durable events where possible; use a transactional outbox for
new delivery needs. A bounded observation-write failure creates explicit coverage
loss without changing the trading decision. Never promise complete evidence after a
failed write.

Keep provider/bot credentials, personal identifiers and unrestricted raw exchange
payloads out of exported content. Live account data remains separately labeled by
LIVE/DEMO and used with its exact time/source provenance. Historical gaps cannot be
recovered merely by adding logging now.

## 11. Persistence, artifacts and exactness

### 11.1 SQLite choice

Single lab process owns its local SQLite file in WAL mode with foreign keys enabled,
short serialized writes and busy timeout. Replay subprocesses write artifacts, not
SQL. API/coordinator writes pass through one repository writer. WAL permits concurrent
readers but one writer; do not use network-mounted SQLite.
[SQLite WAL](https://www.sqlite.org/wal.html)

Use SQLite STRICT tables where supported and canonical decimal TEXT for money,
prices, quantities and exact ratios. Never rely on NUMERIC affinity to preserve
Decimal. Comparison/aggregation uses Decimal in the lab. PostgreSQL migration maps
these fields to the documented numeric precision.

### 11.2 Logical entities

| Entity | Stored content and key guarantees |
|---|---|
| strategy_sources | Runtime/package/source hash and parameter schema |
| studies | Frozen dataset, source, timeframe, protocol, objectives, capital |
| drafts | Owner edits/pins plus optimistic version |
| datasets | Provenance, partition hashes and quality manifest |
| iterations | Sequential ID, owner command, parent, status, immutable effective spec |
| stage_tasks / attempts | Advice/replay/analysis work, lease, fencing, attempt budget |
| results | Scalar metrics, monthly/block results and artifact manifest |
| advisor_exchanges | Exact context/response references, provider, policy and usage |
| observations / skill_revisions | Facts, interpretations, contradictions and playbook |
| exposure_records | Data ranges/versions visible to each lineage and knowledge item |
| live_evidence_batches | Deduplicated sanitized observations and coverage cursor |
| audit_events | Append-only workflow events with stable event IDs |

Detailed fills, equity and large trade lists live in indexed artifacts with paginated
query projections; do not create a SQL row for every market tick.
A strategy may have many studies and a study many iterations. Each iteration has one
frozen effective specification and multiple stage attempts. Each skill revision
references its exact evidence and predecessor.

### 11.3 Atomic publication and reproducibility

Replay writes into a unique attempt staging directory. Finish files, compute hashes,
fsync and atomically rename on the same filesystem. Then commit the result record,
artifact manifest and next task in one short SQL transaction.
Crash before commit leaves an orphan artifact for reconciliation; crash after commit
leaves a durable result. Never expose a partially written result.

Content identity includes:
source/runtime wheel hash, dirty-source hash if permitted, effective parameters,
risk/cost/fill model, dataset, split and metric versions, seeds, dependency lock and
container image. Production exports require a clean versioned source.

Deduplicate accidental identical proposals. Explicit Reproduce performs fresh
execution, stores comparison and does not treat cached results as a rerun.
Money/intent/fill outputs must match under pinned runtime; statistical diagnostic
tolerances are declared separately. Historical bug corrections create new result
versions; preserve originals.

## 12. API contracts and process lifecycle

Browser uses authenticated main-app APIs:
~~~text
GET  /api/experiment-lab/strategies
GET  /api/experiment-lab/studies?strategy_id=...
POST /api/experiment-lab/studies
GET  /api/experiment-lab/studies/{id}/summary
GET  /api/experiment-lab/studies/{id}/iterations?cursor=...
PUT  /api/experiment-lab/studies/{id}/draft
POST /api/experiment-lab/studies/{id}/iterations
     {mode: LLM_NEXT | EXACT | BASELINE, draft_version, idempotency_key}
GET  /api/experiment-lab/iterations/{id}
GET  /api/experiment-lab/iterations/{id}/artifacts/{artifact_id}
POST /api/experiment-lab/iterations/{id}/cancel
POST /api/experiment-lab/iterations/{id}/retry-stage
POST /api/experiment-lab/iterations/{id}/reproduce
POST /api/experiment-lab/studies/{id}/final-evaluation
POST /api/experiment-lab/iterations/{id}/export
GET  /api/experiment-lab/studies/{id}/knowledge
~~~

Commands return 202 and an iteration/task identifier after durable creation.
Use 409 for stale drafts/active-run conflicts, 422 for invalid input.
A response lost after commit is recovered through the idempotency key.

Private lab endpoints under `/internal/v1` provide command/query equivalents plus
claim/heartbeat/complete advisor tasks, bounded evidence retrieval and observation
ingestion. Separate scoped credentials for backend, advisor and exporter:
advisor can claim/complete advice work but cannot create runs or change studies.

Protocol is versioned; OpenAPI schema and representative contract fixtures are
checked in. Verify client/schema drift in CI. Prefer explicit Pydantic DTOs and a
generated or checked typed frontend client; no ORM objects cross boundaries.

Main backend starts no experiment replay job in its request handler.
Advisor worker startup claims only eligible tasks; shutdown cancels provider process
groups and releases/expires leases. Lab startup reconciles abandoned attempts and
artifact manifests before continuing. Activity polling affects display only.

## 13. Deployment, security and operations

Proposed Compose roles:
- existing main backend/frontend;
- `experiment-lab`: lab API/coordinator and one bounded replay subprocess;
- `experiment-advisor`: main-app image with dedicated worker entrypoint.

Use a private lab network with main backend and advisor only; no published lab port.
Lab and advisor have no production DB network, bot-control token, exchange credential
or main MASTER_KEY. Backend-to-lab, advisor-to-lab and exporter tokens have different
capabilities. Provider auth is available only to the app-owned provider role.
Resolve provider auth refresh/concurrency with existing news through the provider
adapter; do not start two unconstrained processes editing shared auth state.

Configure CPU, memory, process, wall-time and disk budgets for both new roles.
Measure current VPS headroom before deployment; an old architecture document's
hardware description is not current capacity evidence. Default replay concurrency is
one. If the host cannot protect trading headroom, run the same lab container on a
separate host with authenticated TLS connectivity.

No provider call gets arbitrary shell/SQL/filesystem tools. Uploaded notes, artifacts
and market text are untrusted context. Resolve artifacts by server IDs and validated
paths, cap archive extraction/response size, redact secrets, and retain audit events.

Provider and lab health degrade independently. Report stage age, lease expiry,
queue length, errors, disk usage and dataset completeness. Mark unavailable usage
metrics honestly. Do not block trading on research health.

Back up SQLite using the online backup API together with referenced immutable
artifacts and manifests; test restore and a reproduction from the restored set.
[SQLite backup API](https://www.sqlite.org/backup.html)
Archive studies; retain failed/rejected experiments. Market cache eviction follows
explicit policy and cannot silently invalidate a reproducibility bundle.

## 14. Implementation delivery plan

Each slice is independently reviewable. Tests listed are acceptance gates to run
during implementation, not claims of completed verification in this planning turn.

| Slice | Deliverable | Evidence needed to finish |
|---|---|---|
| EL0: contracts and characterization | Record ownership decisions, parameter-consumption map, study/metric definitions; capture current source/golden outputs | Owner workflow fixtures and baseline evidence; identify historical-data exposure |
| EL1: pure runtime extraction | Shared wheel, compatibility imports, explicit parameter/risk inputs; no monkey-patching | Existing parity remains green; baseline traces unchanged; every exposed parameter changes its intended computation |
| EL2: deterministic evaluation | Composed replay, complete ledger, corrected metric version, fixed study limits and rankings | First-event loss, month boundaries, open-position cost reconciliation, no-trade/zero-variance and nonpositive equity cases |
| EL3: Binance datasets | Checksummed datasets, trade partitions, UTC resampling, funding/filter provenance, both execution modes | Candle/trade comparison, intrabar ambiguity fixtures, full holding-period coverage, gaps fail visibly |
| EL4: durable lab service | SQLite migrations, single writer, workflows, leases, attempts, artifact publication and CLI integration | Duplicate command, crash at each stage, cancelled late response, disk-full, backup/restore/reproduce |
| EL5: app-owned LLM worker | Reusable provider boundary, advice-task consumer, schemas, evidence budgets and scoped tokens | Provider capability test; strict malformed/invalid/refusal handling; news regression and secret-isolation checks |
| EL6: learning cycle | Versioned skill, observation validation, contradictions, exposure filtering and post-run analysis | Two sequential iterations use prior evidence; third can revert to earlier parent; retry analysis without replay |
| EL7: one-screen UI | Selector, editable/pinned draft, one Run action, simple list, expanded detail and progress | Browser close/refresh survives; one click/one cycle; all requested fields discoverable; stale/error/mobile/keyboard cases |
| EL8: live evidence and timeframe support | Telemetry schema/export, incident reconstruction; 1h and 30m studies with baseline | Bot decision behavior unchanged; no network wait on order path; scope/unit/annualization/timeframe tests |
| EL9: candidate handoff and operations | Export contract, compatibility checker, advisor benchmark, resource limits, restore/runbook and deployment | Same candidate spec replays through application-facing wrapper; no activation; runtime load test and full regressions |

Scope each slice with named API/domain/schema changes, fixtures, migration steps and
rollback notes before coding. EL0 also records the supported parameter bounds and
the explicitly chosen initial-capital value; neither is guessed from mockup numbers.

EL2 establishes metric/selection correctness before exposing an optimizing agent.
EL3 and EL4 can be developed independently once EL0/EL1 contracts exist. UI delivery
can begin with contract fixtures after EL0, but cannot be declared finished before
real API integration. Split each slice into small PRs; do not merge a giant runtime,
LLM and UI rewrite.

### 14.1 File ownership map

~~~text
packages/strategy_runtime/
  contracts.py, parameters.py, trend_rider.py, sizing.py, filters.py

experiments/experiment_lab/
  pyproject.toml, Dockerfile, migrations/
  src/experiment_lab/
    domain/          studies, iterations, knowledge, evaluation policies
    application/     coordinator and use cases; defines required ports
    adapters/        SQLite, artifacts, Binance, runtime/replay
    api/             internal routers and DTOs
    worker/          subprocess supervision
  tests/

backend/app/
  llm/               provider/auth transport
  experiment_advisor/policy/, worker.py, responses.py
  experiment_lab/    thin API facade and typed client
  telemetry/         observation export boundary

frontend/src/features/experiment-lab/
deploy/docker-compose.experiments.yml
docs/architecture/, docs/strategies/, docs/qa/reports/
~~~

Domain has no framework imports. Application depends on domain and its own port
interfaces. Adapters implement ports and depend inward. API composes use cases.
The coordinator owns workflow state, the advisor owns language interpretation,
and the evaluator owns numerical truth. Avoid empty abstraction layers created only
for folder symmetry; split files around tested responsibilities.

## 15. Essential acceptance scenarios

1. New study baseline runs unchanged; first analysis creates skill revision 1.
2. Owner clicks Run next iteration; agent reads baseline/skill 1, selects valid
   unpinned parameters, replay runs and analysis publishes skill 2 without another click.
3. A worse iteration stays recorded. Next proposal can choose the earlier better
   parent and cite the failed assumption. Improvement is never fabricated.
4. Edited/pinned parameter survives LLM advice. Unsupported keys cannot reach replay.
5. Main app or browser stops during replay; result remains durable and analysis
   resumes after advisor recovery.
6. Duplicate click and network retry produce one iteration. Stale worker completion
   cannot override a newer attempt or cancellation.
7. Malformed/out-of-range provider output blocks execution. Provider outage offers
   an explicit manual option; it never silently reuses old advice.
8. Actual trade-path evaluation can differ from OHLC; reports explain changed fills
   and both sets of execution assumptions.
9. First-bar loss and fees on open positions reconcile through equity and monthly
   results. Statistics use known capital boundaries.
10. No feasible candidate leaves the recommended summary empty. Highest-profit result
    remains visible with its failed gates.
11. Reproduce runs fresh inputs and matches the original result; repeated execution
    does not count as new independent learning.
12. Previously used final data cannot reappear as pristine through another study,
    imported report or learned skill.
13. Live observation traces distinguish no signal, blocked signal, failed order and
    actual fill, with missing coverage explicitly marked.
14. Another fixture strategy works through the same service/UI and knowledge scope.
15. Candidate export reconstructs identical intent/fill behavior through an
    application-facing adapter using the pinned shared runtime.
16. Lab and provider process failures leave existing trading services operational.

Required regressions: backend unit/integration and full money-path parity for runtime
changes, lab tests, mypy/Ruff/import boundaries, migrations/restore, frontend unit/
lint/build and applicable full Playwright regression. Mock LLM for deterministic CI;
record one bounded real-provider capability run separately.

## 16. Application compatibility and candidate handoff

Export a declarative candidate bundle:
- strategy family and immutable proposed release ID;
- shared-runtime/schema version and wheel hash;
- complete logic and risk parameters, symbol/timeframe/warmup requirements;
- dataset, metrics, execution and evaluation versions;
- baseline/parent differences, selection exposure and final-evaluation status;
- reports and content hashes, plus known capability limitations.

Provide an import-readiness checker and a developer wrapper generator for the
existing plugin contract. The generator uses approved templates and declarative data;
it does not execute uploaded model-generated Python. Validate plugin identity and
replay parity with the lab before considering registration.

4h candidates can target the current runtime contract after tests. Other timeframes
report `RUNTIME_SUPPORT_REQUIRED` until scheduler/execution policy support is built.
Export success is not selection or activation in the bot. The later release process
retains stopped/flat selection and exchange reconciliation requirements.

## 17. Defaults and scope to approve

- One strategy workspace with studies, one simple route.
- Default owner click permits exactly one LLM-selected candidate cycle.
- Editable seed and pinned values; explicit exact-input/reproduction alternatives.
- First adapter 4h Trend Rider; 1h/30m lab support delivered after baseline integrity.
- SQLite plus Parquet/artifacts; one runner and one advisor initially.
- Main app owns provider configuration and advisor worker; lab owns all workflow state.
- Evolving per-strategy learning playbook with evidence, contradictions and rollback.
- Official Binance trade replay for candidate verification, OHLC mode labeled.
- Profit-first ranking within fixed monthly/drawdown eligibility limits.
- No claim of guaranteed monthly profit or fresh historical holdout without provenance.
- Scope includes candidate compatibility/export and future-learning observations.
- Implementation and deployment begin only after the owner's requested plan review.

This revision replaces the prior plan in place. The reviewed microservice, lab-editing
and learned-skill decisions should be recorded in architecture §8 during EL0 after
plan acceptance. Current application architecture documentation remains descriptive
of what is implemented.

## 18. Research and evidence references

These references informed concrete design decisions; they do not establish trading
profitability:

- [Binance public data](https://github.com/binance/binance-public-data):
  official futures trade/kline schemas, checksums and archive corrections (§8).
- [SQLite WAL](https://www.sqlite.org/wal.html):
  local-file and single-writer constraints (§11).
- [SQLite online backup](https://www.sqlite.org/backup.html):
  consistent backups (§13).
- [QuantConnect parameter optimization](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters):
  tuned periods become in-sample (§9).
- [QuantConnect walk-forward guidance](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization):
  chronological evaluation design; our fixed-candidate block tests are explicitly
  distinguished from an adaptive retraining simulation (§9).

Code evidence is in §2. Historical reports and earlier memory were used to locate
the existing lab, then checked against the current source. No historical performance
numbers are offered as current results in this plan.
