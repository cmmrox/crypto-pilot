"""Synthetic fixtures exercise workflow correctness, never profitability evidence."""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.binance import validate_dataset
from experiment_lab.adapters.provenance import runtime_hash
from experiment_lab.adapters.replay import Replay
from experiment_lab.adapters.store import Conflict, Store
from experiment_lab.api import create_app
from experiment_lab.application.service import LabService
from experiment_lab.domain.models import IterationInput, StudyInput
from experiment_lab.settings import Settings
from strategy_runtime.parameters import validate_parameters


@pytest.fixture
def lab(tmp_path):
    artifacts = Artifacts(tmp_path / "artifacts")
    store = Store(tmp_path / "lab.sqlite3")
    return LabService(store, artifacts, runtime_hash, validate_dataset)


def dataset():
    start = pd.Timestamp("2024-01-01", tz="UTC")
    end = start + pd.Timedelta(days=4)
    times = pd.date_range(
        start - pd.Timedelta(hours=400 * 4), end, freq="4h", inclusive="left"
    )
    return {
        "source": "BINANCE_USDM_PUBLIC",
        "test_fixture": True,
        "symbol": "BTCUSDT",
        "interval": "4h",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "candles": [
            {
                "dt": t.isoformat(),
                "open": "40000",
                "high": "40010",
                "low": "39990",
                "close": "40000",
                "volume": "1",
            }
            for t in times
        ],
        "funding": [
            {"dt": t.isoformat(), "funding_rate": "0.0001", "mark_price": "40000"}
            for t in pd.date_range(start, end, freq="8h", inclusive="left")
        ],
        "filters": {
            "step_size": "0.001",
            "min_qty": "0.001",
            "max_qty": "120",
            "tick_size": "0.1",
            "min_notional": "50",
        },
    }


def test_mixed_iso_funding_precision_is_supported(lab):
    data = dataset()
    data["funding"][1]["dt"] = data["funding"][1]["dt"].replace(
        "+00:00", ".001000+00:00"
    )
    identity = lab.artifacts.put(data)
    parent = lab.create_study(
        StudyInput(
            name="Funding millisecond regression",
            dataset_id=identity,
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
        )
    )
    first = complete_baseline(lab, parent["id"])
    assert first["status"] == "COMPLETED"


def study(lab):
    data = dataset()
    identity = lab.artifacts.put(data)
    return lab.create_study(
        StudyInput(
            name="Synthetic workflow fixture",
            dataset_id=identity,
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            pinned=["risk_pct"],
        )
    )


def review(iteration_id):
    return {
        "summary": "Flat test prices generated no trades.",
        "lesson": "No-trade output is not profitable evidence.",
        "counterevidence": "Synthetic fixture cannot validate a trading hypothesis.",
        "next_hypothesis": "Test a real regime change.",
        "evidence_ids": [iteration_id],
    }


def complete_baseline(lab, identity):
    run = lab.start(identity, IterationInput(), "baseline-1")
    job = lab.store.claim("REPLAY")
    output = Replay(lab.artifacts).run(lab.context(run["id"]))
    lab.complete(job["id"], job["token"], output)
    job = lab.store.claim("REVIEW")
    lab.complete(job["id"], job["token"], review(run["id"]))
    return lab.store.iteration(run["id"])


def test_baseline_then_advised_cycle_and_learning(lab):
    parent = study(lab)
    first = complete_baseline(lab, parent["id"])
    assert first["status"] == "COMPLETED"
    assert first["parameters"] == validate_parameters({})
    assert Decimal(first["result"]["metrics"]["net_profit"]) == 0
    assert len(lab.store.lessons(parent["id"])) == 1
    second = lab.start(parent["id"], IterationInput(), "second-run")
    job = lab.store.claim("SELECT")
    context = lab.context(second["id"])
    assert context["history"][0]["id"] == first["id"]
    assert context["lessons"][0]["revision"] == 1
    advice = {
        "parameters": first["parameters"] | {"stop_atr": "2.6"},
        "hypothesis": "Small change",
        "evidence_ids": [first["id"]],
        "uncertainty": "Low sample size",
        "falsification": "Worse drawdown",
    }
    lab.complete(job["id"], job["token"], advice)
    replay = lab.store.claim("REPLAY")
    result = Replay(lab.artifacts).run(lab.context(second["id"]))
    lab.complete(replay["id"], replay["token"], result)
    review_job = lab.store.claim("REVIEW")
    lab.complete(review_job["id"], review_job["token"], review(second["id"]))
    assert len(lab.store.lessons(parent["id"])) == 2
    assert lab.store.claim("SELECT") is None
    assert lab.store.claim("REPLAY") is None
    assert lab.store.claim("REVIEW") is None


def test_idempotency_and_one_active_run(lab):
    identity = study(lab)["id"]
    first = lab.start(identity, IterationInput(), "same-command")
    assert lab.start(identity, IterationInput(), "same-command")["id"] == first["id"]
    with pytest.raises(Conflict):
        lab.start(identity, IterationInput(mode="MANUAL"), "same-command")
    with pytest.raises(Conflict):
        lab.start(identity, IterationInput(), "another-command")


def test_cancel_rejects_late_worker(lab):
    identity = study(lab)["id"]
    run = lab.start(identity, IterationInput(), "cancel-run")
    job = lab.store.claim("REPLAY")
    lab.store.cancel(run["id"])
    with pytest.raises(Conflict):
        lab.store.finish(job["id"], job["token"], {})


def test_expired_lease_is_fenced(lab):
    identity = study(lab)["id"]
    lab.start(identity, IterationInput(), "lease-run")
    first = lab.store.claim("REPLAY", lease_seconds=-1)
    second = lab.store.claim("REPLAY")
    assert first["id"] == second["id"]
    with pytest.raises(Conflict):
        lab.store.finish(first["id"], first["token"], {})


def test_invalid_advice_cannot_change_pinned_risk(lab):
    identity = study(lab)["id"]
    first = complete_baseline(lab, identity)
    lab.start(identity, IterationInput(), "bad-advice")
    job = lab.store.claim("SELECT")
    with pytest.raises(ValueError, match="pinned"):
        lab.complete(
            job["id"],
            job["token"],
            {
                "parameters": first["parameters"] | {"risk_pct": "10"},
                "hypothesis": "Reduce risk",
                "evidence_ids": [first["id"]],
                "uncertainty": "Unknown",
                "falsification": "No improvement",
            },
        )
    assert lab.store.claim("REPLAY") is None


@pytest.mark.parametrize(
    "values",
    [
        {"stop_atr": "NaN"},
        {"stop_atr": "2.55"},
        {"unknown": "1"},
        {"fast_period": "50", "medium_period": "20"},
        {"risk_pct": "100"},
    ],
)
def test_parameter_guards(values):
    with pytest.raises(ValueError):
        validate_parameters(values)


def test_artifact_tampering_detected(lab):
    identity = lab.artifacts.put({"money": "0.00000001"})
    assert lab.artifacts.get(identity) == {"money": "0.00000001"}
    (lab.artifacts.root / f"{identity}.json").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        lab.artifacts.get(identity)


def test_http_auth_and_restart(tmp_path):
    config = Settings(data_dir=tmp_path, service_token="x" * 32)
    app = create_app(config)
    with TestClient(app) as client:
        assert client.get("/studies").status_code == 401
        assert (
            client.get(
                "/strategies", headers={"Authorization": "Bearer " + "x" * 32}
            ).status_code
            == 200
        )
    assert Store(tmp_path / "lab.sqlite3").studies() == []


def test_scoped_workers_cannot_create_studies_or_claim_other_stages(tmp_path):
    config = Settings(
        data_dir=tmp_path,
        service_token="o" * 32,
        advisor_token="a" * 32,
        runner_token="r" * 32,
    )
    with TestClient(create_app(config)) as client:
        owner = {"Authorization": "Bearer " + "o" * 32}
        advisor = {"Authorization": "Bearer " + "a" * 32}
        runner = {"Authorization": "Bearer " + "r" * 32}
        assert client.post("/studies", headers=advisor, json={}).status_code == 403
        assert (
            client.post(
                "/jobs/claim", headers=advisor, json={"kind": "REPLAY"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/jobs/claim", headers=runner, json={"kind": "SELECT"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/jobs/claim", headers=owner, json={"kind": "SELECT"}
            ).status_code
            == 403
        )
        assert (
            client.post("/jobs/claim", headers=advisor, json={"kind": "SELECT"}).json()
            is None
        )
        assert (
            client.post("/jobs/claim", headers=runner, json={"kind": "REPLAY"}).json()
            is None
        )


def test_scoped_credentials_must_be_distinct(tmp_path):
    with pytest.raises(ValueError, match="distinct"):
        Settings(data_dir=tmp_path, service_token="a" * 32, advisor_token="a" * 32)


def test_newer_database_is_rejected_without_schema_writes(tmp_path):
    import sqlite3

    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="newer"):
        Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master").fetchall() == []
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99


def test_strategy_learning_keeps_cross_study_scope(lab):
    first_study = study(lab)
    baseline = complete_baseline(lab, first_study["id"])
    second_study = study(lab)
    run = lab.start(second_study["id"], IterationInput(), "new-study-baseline")
    context = lab.context(run["id"])
    assert context["history"] == []
    evidence = context["strategy_lessons"][0]
    assert evidence["iteration_id"] == baseline["id"]
    assert evidence["scope"]["dataset_id"] == first_study["config"]["dataset_id"]
    assert evidence["scope"]["interval"] == "4h"
    assert evidence["status"] == "OBSERVED"
    assert lab.store.claim("SELECT") is None


def test_reproduction_rejects_different_metrics_and_retains_evidence(lab):
    identity = study(lab)["id"]
    first = complete_baseline(lab, identity)
    assert (
        lab.artifacts.get(first["result"]["decision_record_id"])["output"]["metrics"]
        == first["result"]["metrics"]
    )
    run = lab.start(
        identity,
        IterationInput(mode="REPRODUCE", source_iteration_id=first["id"]),
        "repeat-regression",
    )
    job = lab.store.claim("REPLAY")
    result = Replay(lab.artifacts).run(lab.context(run["id"]))
    artifact = lab.artifacts.get(result["artifact_id"])
    metrics = result["metrics"] | {"net_profit": "1"}
    altered_id = lab.artifacts.put(artifact | {"metrics": metrics})
    with pytest.raises(ValueError, match="Reproduction differs"):
        lab.complete(
            job["id"], job["token"], {"artifact_id": altered_id, "metrics": metrics}
        )
    assert lab.store.claim("REVIEW") is None


def test_failed_review_can_resume_without_rerunning_replay(lab):
    identity = study(lab)["id"]
    run = lab.start(identity, IterationInput(), "failed-review")
    replay = lab.store.claim("REPLAY")
    result = Replay(lab.artifacts).run(lab.context(run["id"]))
    lab.complete(replay["id"], replay["token"], result)
    job = lab.store.claim("REVIEW")
    lab.store.fail(job["id"], job["token"])
    saved = lab.store.iteration(run["id"])["result"]
    lab.store.retry_review(run["id"])
    assert lab.store.claim("REPLAY") is None
    retried = lab.store.claim("REVIEW")
    assert retried["token"] != job["token"]
    lab.complete(retried["id"], retried["token"], review(run["id"]))
    assert lab.store.iteration(run["id"])["result"] == saved
    assert len(lab.store.lessons(identity)) == 1
