# Atlas 7 release 1.2 cutover and rollback

Status: local implementation and QA only. No production deployment is authorized by
this task. See `docs/qa/reports/ATLAS-7-EXECUTION-PARITY-2026-10-05.md` for evidence and
outstanding release gates.

## Release gates

1. Review this branch and the execution contract. Require green backend, strategy
   parity, recovery, lint/types/import boundaries, frontend production build and
   desktop/mobile QA. Retain the exact reviewed revision and built images.
2. Validate both long and short lifecycle on a dedicated flat Binance DEMO account:
   entry fill, CONTRACT_PRICE algo stop, lot-rounded LIMIT TP1, full/partial-fill
   reconciliation, immediate breakeven, individual stop replacement/cancellation,
   reconnect/restart recovery and final flat/order-free cleanup. Never reuse an
   account with an existing position/order. Dedicated flat-DEMO exchange acceptance
   remains pending; local software tests do not replace it.
3. Owner approves production release. Confirm LIVE gates, account permissions,
   isolated one-way/single-asset BTCUSDT configuration, 3x leverage cap, current
   active strategy and actual flat/order-free account truth. An existing 1.1 trade
   must finish under its original policy before cutover. Do not manually change
   stops or flatten that trade as part of this local task.
4. Stop trading, confirm one backend worker, back up the database and record current
   image revision, settings, breaker events, latest candle cursor and account truth.
5. Apply Alembic revision `d9e0f1a2b3c4` (three nullable equity snapshot fields). No
   credential migration or alteration of old trades is required. Deploy the reviewed
   backend/frontend together. Keep LIVE entry gates closed during health checks.
6. Verify authentication, strategy release 1.2, gap-free closed-candle history,
   worker heartbeat, user-stream recovery, duplicate-close suppression and target
   fields. Re-read account truth before explicitly starting the bot. Observe the
   first real finalized close and execution timing; do not claim a historical replay
   as a live fill or profitability result.

## Failure / rollback

Enter safe mode to block entries while protection recovery continues. If exposure is
open, verify active exchange stops and order truth before any operational action;
never roll back code in the middle of a PENDING stop replacement. Reconcile the exact
client IDs and confirm remaining quantity. Owner controls any production trade action.

Once flat/order-free and stopped, restore the prior reviewed images. Keep the additive
nullable columns; older code ignores them. A schema downgrade is optional only after
backup and while stopped: downgrade to `c8d9e0f1a2b3` removes the three new snapshot
fields, not orders/trades. Restore from backup if schema/data recovery is necessary.
Retain audit events and artifacts and document the failure before restarting.
