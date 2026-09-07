"""SQLite owns all state transitions, idempotency and expiring work leases."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from decimal import Decimal
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from experiment_lab.adapters.artifacts import canonical
from experiment_lab.domain.errors import Conflict as Conflict
from experiment_lab.domain.failures import FAILURES

SCHEMA_VERSION = 3

INDEX_MIGRATION = """
CREATE INDEX IF NOT EXISTS jobs_pending ON jobs(kind, expires) WHERE done=0;
CREATE INDEX IF NOT EXISTS lessons_study_revision ON lessons(study_id, revision);
CREATE INDEX IF NOT EXISTS lessons_created ON lessons(created DESC);
CREATE INDEX IF NOT EXISTS studies_strategy ON studies(json_extract(config, '$.strategy_id'));
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS studies (
 id TEXT PRIMARY KEY, config TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS iterations (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
 ordinal INTEGER NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
 request_key TEXT NOT NULL, request TEXT NOT NULL, parameters TEXT NOT NULL,
 advice TEXT, result TEXT, review TEXT, error TEXT, created REAL NOT NULL,
 UNIQUE(study_id, ordinal), UNIQUE(study_id, request_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_iteration ON iterations(study_id)
 WHERE status NOT IN ('COMPLETED','FAILED','CANCELLED');
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, iteration_id TEXT NOT NULL REFERENCES iterations(id),
 kind TEXT NOT NULL, token TEXT, expires REAL, attempts INTEGER NOT NULL DEFAULT 0,
 done INTEGER NOT NULL DEFAULT 0, UNIQUE(iteration_id, kind)
);
CREATE TABLE IF NOT EXISTS lessons (
 id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
 iteration_id TEXT NOT NULL UNIQUE REFERENCES iterations(id), revision INTEGER NOT NULL,
 status TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS exposures (
 dataset_id TEXT NOT NULL, study_id TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 purpose TEXT NOT NULL, UNIQUE(dataset_id, study_id, start, end)
);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY, iteration_id TEXT NOT NULL, event TEXT NOT NULL,
 detail TEXT NOT NULL, created REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this Lab release")
            db.execute("PRAGMA journal_mode=WAL")
            if current == 0:
                db.executescript(
                    "BEGIN IMMEDIATE;\n" + SCHEMA + "\nPRAGMA user_version=1;\nCOMMIT;"
                )
            if current < 2:
                db.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + INDEX_MIGRATION
                    + "\nPRAGMA user_version=2;\nCOMMIT;"
                )

            if current < 3:
                db.executescript(
                    "BEGIN IMMEDIATE; CREATE INDEX IF NOT EXISTS studies_created "
                    "ON studies(created DESC,id DESC); PRAGMA user_version=3; COMMIT;"
                )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def create_study(self, config: dict) -> dict:
        identity = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute(
                "INSERT INTO studies VALUES (?,?,?)",
                (identity, canonical(config), time.time()),
            )
        return self.study(identity)

    def studies(self, before_id: str | None = None, limit: int = 50) -> list[dict]:
        with self.connection() as db:
            cursor = (
                db.execute(
                    "SELECT created,id FROM studies WHERE id=?", (before_id,)
                ).fetchone()
                if before_id
                else None
            )
            if before_id and cursor is None:
                raise KeyError("Study cursor not found")
            return [
                dict(row) | {"config": json.loads(row["config"])}
                for row in db.execute(
                    "SELECT * FROM studies WHERE (created,id)<(?,?) ORDER BY created DESC,id DESC LIMIT ?",
                    (
                        cursor["created"] if cursor else float("inf"),
                        cursor["id"] if cursor else "",
                        limit,
                    ),
                )
            ]

    def study(self, identity: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM studies WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise KeyError("Study not found")
            return dict(row) | {"config": json.loads(row["config"])}

    def iterations(self, study_id: str) -> list[dict]:
        with self.connection() as db:
            return [
                self.decode(row)
                for row in db.execute(
                    "SELECT * FROM iterations WHERE study_id=? ORDER BY ordinal DESC",
                    (study_id,),
                )
            ]

    def iteration_page(
        self, study_id: str, before: int | None = None, limit: int = 50
    ) -> dict:
        """Keyset paging remains stable when a new run is added between requests."""
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM iterations WHERE study_id=? AND ordinal<? ORDER BY ordinal DESC LIMIT ?",
                (study_id, before or 2**63 - 1, limit + 1),
            ).fetchall()
        return {
            "iterations": [self.decode(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["ordinal"] if len(rows) > limit else None,
        }

    def summary(self, study_id: str, before: int = 2**63 - 1) -> dict:
        """Scan only scalar projections, never historical JSON blobs or float money.

        SQLite REAL would lose decimal precision when ranking money. Stream the
        small profit projection with Decimal; only the winning record is decoded.
        """
        with self.connection() as db:
            counts = dict(
                db.execute(
                    "SELECT status,count(*) FROM iterations WHERE study_id=? AND ordinal<? GROUP BY status",
                    (study_id, before),
                )
            )
            best_id = None
            best_profit = None
            for row in db.execute(
                "SELECT id,json_extract(result,'$.metrics.net_profit') AS profit FROM iterations "
                "WHERE study_id=? AND ordinal<? AND result IS NOT NULL ORDER BY ordinal DESC",
                (study_id, before),
            ):
                profit = Decimal(row["profit"])
                if best_profit is None or profit > best_profit:
                    best_id, best_profit = row["id"], profit
        return {
            "total_iterations": sum(counts.values()),
            "completed_iterations": counts.get("COMPLETED", 0),
            "failed_count": counts.get("FAILED", 0),
            "active": any(
                count
                for status, count in counts.items()
                if status not in ("COMPLETED", "FAILED", "CANCELLED")
            ),
            "highest_profit_iteration_id": best_id,
            "highest_profit_iteration": self.iteration(best_id) if best_id else None,
        }

    def history_context(self, study_id: str, before: int) -> dict:
        """Bound decoded history while retaining the baseline and best ancestor."""
        recent = self.iteration_page(study_id, before, 20)["iterations"]
        summary = self.summary(study_id, before)
        selected = {row["id"]: row for row in recent}
        with self.connection() as db:
            baseline = db.execute(
                "SELECT * FROM iterations WHERE study_id=? AND ordinal<? AND result IS NOT NULL ORDER BY ordinal LIMIT 1",
                (study_id, before),
            ).fetchone()
            failures = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM iterations WHERE study_id=? AND ordinal<? AND status='FAILED' ORDER BY ordinal DESC LIMIT 20",
                    (study_id, before),
                )
            ]
        for row in (
            self.decode(baseline) if baseline else None,
            summary["highest_profit_iteration"],
        ):
            if row:
                selected[row["id"]] = row
        return {
            "history": sorted(
                selected.values(), key=lambda row: row["ordinal"], reverse=True
            ),
            "history_total": summary["total_iterations"],
            "failed_iterations": failures,
            "failed_count": summary["failed_count"],
        }

    @staticmethod
    def decode(row: sqlite3.Row) -> dict:
        result = dict(row)
        for key in ("request", "parameters", "advice", "result", "review"):
            if result.get(key) is not None:
                result[key] = json.loads(result[key])
        return result

    def iteration(self, identity: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM iterations WHERE id=?", (identity,)
            ).fetchone()
            if row is None:
                raise KeyError("Iteration not found")
            return self.decode(row)

    def create_iteration(
        self, study_id: str, key: str, request: dict, parameters: dict
    ) -> dict:
        with self.transaction() as db:
            old = db.execute(
                "SELECT * FROM iterations WHERE study_id=? AND request_key=?",
                (study_id, key),
            ).fetchone()
            if old:
                if old["request"] != canonical(request):
                    raise Conflict(
                        "Idempotency key already used for a different request"
                    )
                return self.decode(old)
            ordinal = db.execute(
                "SELECT COALESCE(MAX(ordinal),0)+1 FROM iterations WHERE study_id=?",
                (study_id,),
            ).fetchone()[0]
            identity = uuid.uuid4().hex
            mode = request["mode"]
            has_baseline = (
                db.execute(
                    "SELECT 1 FROM iterations WHERE study_id=? AND result IS NOT NULL LIMIT 1",
                    (study_id,),
                ).fetchone()
                is not None
            )
            kind = "SELECT" if mode == "ADVISED" and has_baseline else "REPLAY"
            try:
                db.execute(
                    "INSERT INTO iterations (id,study_id,ordinal,mode,status,request_key,request,parameters,created) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        identity,
                        study_id,
                        ordinal,
                        mode,
                        f"WAITING_{kind}",
                        key,
                        canonical(request),
                        canonical(parameters),
                        time.time(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise Conflict("This study already has an active iteration") from error
            self.enqueue(db, identity, kind)
        return self.iteration(identity)

    @staticmethod
    def enqueue(db: sqlite3.Connection, iteration_id: str, kind: str) -> None:
        db.execute(
            "INSERT INTO audit_events(iteration_id,event,detail,created) VALUES (?,?,?,?)",
            (iteration_id, "TASK_QUEUED", kind, time.time()),
        )
        db.execute(
            "INSERT INTO jobs (id,iteration_id,kind) VALUES (?,?,?)",
            (uuid.uuid4().hex, iteration_id, kind),
        )

    def claim(self, kind: str, lease_seconds: int = 180) -> dict | None:
        now = time.time()
        with self.transaction() as db:
            # A crashed worker gets at most three attempts; no invisible infinite retries.
            exhausted = db.execute(
                "SELECT j.iteration_id FROM jobs j JOIN iterations i ON i.id=j.iteration_id WHERE j.done=0 AND j.attempts>=3 AND j.expires<? AND i.status NOT IN ('CANCELLED','FAILED','COMPLETED')",
                (now,),
            ).fetchall()
            for item in exhausted:
                db.execute(
                    "UPDATE iterations SET status='FAILED',error='Worker lease expired after three attempts' WHERE id=?",
                    (item[0],),
                )
                db.execute("UPDATE jobs SET done=1 WHERE iteration_id=?", (item[0],))
                db.execute(
                    "INSERT INTO audit_events(iteration_id,event,detail,created) VALUES (?,?,?,?)",
                    (item[0], "TASK_FAILED", "LEASE_EXHAUSTED", now),
                )
            row = db.execute(
                "SELECT j.* FROM jobs j JOIN iterations i ON i.id=j.iteration_id WHERE j.kind=? AND j.done=0 AND j.attempts<3 AND (j.expires IS NULL OR j.expires<?) AND i.status NOT IN ('CANCELLED','FAILED','COMPLETED') ORDER BY i.created LIMIT 1",
                (kind, now),
            ).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute(
                "UPDATE jobs SET token=?,expires=?,attempts=attempts+1 WHERE id=?",
                (token, now + lease_seconds, row["id"]),
            )
            db.execute(
                "UPDATE iterations SET status=? WHERE id=?",
                (f"RUNNING_{kind}", row["iteration_id"]),
            )
            return dict(row) | {"token": token, "expires": now + lease_seconds}

    def checked_job(
        self, db: sqlite3.Connection, identity: str, token: str
    ) -> sqlite3.Row:
        row = db.execute(
            "SELECT j.*,i.status FROM jobs j JOIN iterations i ON i.id=j.iteration_id WHERE j.id=?",
            (identity,),
        ).fetchone()
        if (
            row is None
            or row["token"] != token
            or row["done"]
            or row["expires"] < time.time()
            or row["status"] in ("CANCELLED", "FAILED", "COMPLETED")
        ):
            raise Conflict("Lease is stale or iteration is no longer active")
        return row

    def heartbeat(self, identity: str, token: str) -> None:
        with self.transaction() as db:
            self.checked_job(db, identity, token)
            db.execute(
                "UPDATE jobs SET expires=? WHERE id=?", (time.time() + 180, identity)
            )

    def job(self, identity: str, token: str) -> dict:
        with self.connection() as db:
            return dict(self.checked_job(db, identity, token))

    def finish(self, identity: str, token: str, output: dict) -> str:
        with self.transaction() as db:
            job = self.checked_job(db, identity, token)
            iteration_id, kind = job["iteration_id"], job["kind"]
            if kind == "SELECT":
                db.execute(
                    "UPDATE iterations SET parameters=?,advice=?,status='WAITING_REPLAY' WHERE id=?",
                    (canonical(output["parameters"]), canonical(output), iteration_id),
                )
                self.enqueue(db, iteration_id, "REPLAY")
            elif kind == "REPLAY":
                db.execute(
                    "UPDATE iterations SET result=?,status='WAITING_REVIEW' WHERE id=?",
                    (canonical(output), iteration_id),
                )
                self.enqueue(db, iteration_id, "REVIEW")
            else:
                row = db.execute(
                    "SELECT * FROM iterations WHERE id=?", (iteration_id,)
                ).fetchone()
                revision = db.execute(
                    "SELECT COUNT(*)+1 FROM lessons WHERE study_id=?",
                    (row["study_id"],),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO lessons VALUES (?,?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        row["study_id"],
                        iteration_id,
                        revision,
                        "REPRODUCTION" if row["mode"] == "REPRODUCE" else "OBSERVED",
                        canonical(output),
                        time.time(),
                    ),
                )
                db.execute(
                    "UPDATE iterations SET review=?,status='COMPLETED' WHERE id=?",
                    (canonical(output), iteration_id),
                )
            db.execute("UPDATE jobs SET done=1 WHERE id=?", (identity,))
            db.execute(
                "INSERT INTO audit_events(iteration_id,event,detail,created) VALUES (?,?,?,?)",
                (iteration_id, "TASK_COMPLETED", kind, time.time()),
            )
            return iteration_id

    def retry_review(self, identity: str) -> None:
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM iterations WHERE id=?", (identity,)
            ).fetchone()
            if row is None:
                raise KeyError("Iteration not found")
            if row["status"] in ("WAITING_REVIEW", "RUNNING_REVIEW"):
                return
            if row["status"] != "FAILED" or row["result"] is None:
                raise Conflict(
                    "Only a failed review with a saved replay can be retried"
                )
            try:
                db.execute(
                    "UPDATE iterations SET status='WAITING_REVIEW',error=NULL WHERE id=?",
                    (identity,),
                )
            except sqlite3.IntegrityError as error:
                raise Conflict("Another iteration is active") from error
            db.execute(
                "UPDATE jobs SET done=0,token=NULL,expires=NULL,attempts=0 WHERE iteration_id=? AND kind='REVIEW'",
                (identity,),
            )
            db.execute(
                "INSERT INTO audit_events(iteration_id,event,detail,created) VALUES (?,?,?,?)",
                (
                    identity,
                    "REVIEW_RETRIED",
                    "Owner requested review only; replay preserved",
                    time.time(),
                ),
            )

    def fail(
        self, identity: str, token: str, error_code: str = "WORKER_FAILED"
    ) -> None:
        with self.transaction() as db:
            job = self.checked_job(db, identity, token)
            db.execute(
                "UPDATE iterations SET status='FAILED',error=? WHERE id=?",
                (
                    f"{job['kind']}: {FAILURES[error_code]}",
                    job["iteration_id"],
                ),
            )
            db.execute("UPDATE jobs SET done=1 WHERE id=?", (identity,))
            db.execute(
                "INSERT INTO audit_events(iteration_id,event,detail,created) VALUES (?,?,?,?)",
                (job["iteration_id"], "TASK_FAILED", error_code, time.time()),
            )

    def cancel(self, identity: str) -> None:
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE iterations SET status='CANCELLED' WHERE id=? AND status NOT IN ('FAILED','COMPLETED','CANCELLED')",
                (identity,),
            ).rowcount
            if changed:
                db.execute("UPDATE jobs SET done=1 WHERE iteration_id=?", (identity,))
                db.execute(
                    "INSERT INTO audit_events(iteration_id,event,detail,created) VALUES (?,?,?,?)",
                    (
                        identity,
                        "ITERATION_CANCELLED",
                        "Owner cancelled iteration",
                        time.time(),
                    ),
                )

    def lessons(self, study_id: str, limit: int | None = None) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row) | {"content": json.loads(row["content"])}
                for row in db.execute(
                    "SELECT * FROM (SELECT * FROM lessons WHERE study_id=? ORDER BY revision DESC LIMIT ?) ORDER BY revision",
                    (study_id, -1 if limit is None else limit),
                )
            ]

    def expose(self, study_id: str, config: dict) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO exposures VALUES (?,?,?,?,?)",
                (
                    config["dataset_id"],
                    study_id,
                    config["start"],
                    config["end"],
                    "DEVELOPMENT_EXPOSED",
                ),
            )

    def strategy_lessons(self, strategy_id: str, limit: int = 20) -> list[dict]:
        """Retrieve bounded cross-study evidence with its original comparison scope."""
        with self.connection() as db:
            rows = db.execute(
                "SELECT l.*, s.config, i.parameters, i.result FROM lessons l "
                "JOIN studies s ON s.id=l.study_id JOIN iterations i ON i.id=l.iteration_id "
                "WHERE json_extract(s.config, '$.strategy_id')=? "
                "ORDER BY l.created DESC LIMIT ?",
                (strategy_id, min(max(limit, 1), 50)),
            ).fetchall()
            evidence = []
            for row in rows:
                scope = json.loads(row["config"])
                result = json.loads(row["result"])
                evidence.append(
                    {
                        "iteration_id": row["iteration_id"],
                        "study_id": row["study_id"],
                        "revision": row["revision"],
                        "status": row["status"],
                        "content": json.loads(row["content"]),
                        "parameters": json.loads(row["parameters"]),
                        "metrics": result["metrics"],
                        "scope": {
                            key: scope[key]
                            for key in (
                                "dataset_id",
                                "start",
                                "end",
                                "interval",
                                "fidelity",
                                "initial_capital",
                                "runtime_hash",
                            )
                        },
                    }
                )
            return evidence
