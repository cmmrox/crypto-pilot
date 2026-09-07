"""Release regressions: bounded histories, strict requests and durable operations."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from experiment_lab.adapters.store import Store
from experiment_lab.api import create_app
from experiment_lab.domain.models import StudyInput
from experiment_lab.settings import Settings


def populate(store, count=125):
    parent = store.create_study(
        {"name": "Volume fixture", "strategy_id": "trend_rider_v6_4h"}
    )
    with store.transaction() as db:
        for ordinal in range(1, count + 1):
            result = json.dumps({"metrics": {"net_profit": str(ordinal)}})
            db.execute(
                "INSERT INTO iterations (id,study_id,ordinal,mode,status,request_key,request,parameters,result,created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f"{ordinal:032x}",
                    parent["id"],
                    ordinal,
                    "ADVISED",
                    "COMPLETED",
                    str(ordinal),
                    "{}",
                    "{}",
                    result,
                    ordinal,
                ),
            )
    return parent


def test_study_pages_keep_global_summary_and_stable_cursor(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, service_token="o" * 32))
    store = app.state.service.store
    parent = populate(store)
    headers = {"Authorization": "Bearer " + "o" * 32}
    with TestClient(app) as client:
        page = client.get(f"/studies/{parent['id']}?limit=20", headers=headers).json()
        assert len(page["iterations"]) == 20
        assert page["total_iterations"] == 125
        assert page["completed_iterations"] == 125
        assert page["highest_profit_iteration"]["ordinal"] == 125
        assert page["next_cursor"] == 106
        older = client.get(
            f"/studies/{parent['id']}?limit=20&before=106", headers=headers
        ).json()
        assert older["iterations"][0]["ordinal"] == 105
        assert not {row["id"] for row in page["iterations"]} & {
            row["id"] for row in older["iterations"]
        }
        assert (
            client.get(
                f"/studies/{parent['id']}?limit=1001", headers=headers
            ).status_code
            == 422
        )


def test_history_context_decodes_only_recent_baseline_and_best(tmp_path):
    store = Store(tmp_path / "lab.sqlite3")
    parent = populate(store, 2000)
    with patch.object(store, "decode", wraps=store.decode) as decode:
        context = store.history_context(parent["id"], before=2001)
        assert context["history_total"] == 2000
        assert len(context["history"]) == 21
        assert context["history"][-1]["ordinal"] == 1
        assert context["history"][0]["ordinal"] == 2000
        assert decode.call_count <= 22


def test_invalid_capital_returns_validation_error_not_server_error():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        StudyInput(
            name="Bad input",
            dataset_id="a" * 64,
            start="2024-01-01T00:00:00Z",
            end="2024-02-01T00:00:00Z",
            initial_capital="not-money",
        )


def test_cancel_finishes_pending_jobs_and_audits_once(tmp_path):
    store = Store(tmp_path / "lab.sqlite3")
    parent = store.create_study({})
    run = store.create_iteration(
        parent["id"], "cancel-command", {"mode": "ADVISED"}, {}
    )
    store.cancel(run["id"])
    store.cancel(run["id"])
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE done=0").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE event='ITERATION_CANCELLED'"
            ).fetchone()[0]
            == 1
        )


def test_private_api_rejects_oversized_chunked_body(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, service_token="o" * 32))
    with TestClient(app) as client:
        response = client.post(
            "/studies",
            headers={"Authorization": "Bearer " + "o" * 32},
            content=iter([b"x" * 600_000, b"y" * 600_000]),
        )
        assert response.status_code == 413
        assert (
            client.get(
                "/health", headers={"Authorization": "Bearer " + "o" * 32}
            ).status_code
            == 200
        )
        assert client.get("/openapi.json").status_code == 404


def test_exhausted_worker_leases_finish_once_and_survive_restart(tmp_path):
    path = tmp_path / "lab.sqlite3"
    store = Store(path)
    parent = store.create_study({})
    run = store.create_iteration(parent["id"], "crash-command", {"mode": "ADVISED"}, {})
    for _ in range(3):
        assert store.claim("REPLAY", lease_seconds=-1)
    assert store.claim("REPLAY") is None
    assert Store(path).iteration(run["id"])["status"] == "FAILED"
    assert store.claim("REPLAY") is None
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE done=0").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE detail='LEASE_EXHAUSTED'"
            ).fetchone()[0]
            == 1
        )


def test_schema_one_upgrade_preserves_existing_records(tmp_path):
    import sqlite3
    from experiment_lab.adapters.store import SCHEMA, SCHEMA_VERSION

    path = tmp_path / "lab.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA + "PRAGMA user_version=1;")
        db.execute("INSERT INTO studies VALUES ('existing','{}',0)")
    store = Store(path)
    assert store.study("existing")["config"] == {}
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_artifact_flush_failure_cleans_temporary_file(tmp_path, monkeypatch):
    import errno
    from experiment_lab.adapters.artifacts import Artifacts

    artifacts = Artifacts(tmp_path / "artifacts")

    def full(*args):
        raise OSError(errno.ENOSPC, "Disk full")

    monkeypatch.setattr("experiment_lab.adapters.artifacts.os.fsync", full)
    with pytest.raises(OSError):
        artifacts.put({"durable": False})
    assert list(artifacts.root.iterdir()) == []
