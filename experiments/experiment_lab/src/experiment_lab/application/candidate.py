"""Declarative handoff only. Export never selects, registers or activates a plugin."""

from experiment_lab.application.ports import ArtifactStore, ResearchRepository
from experiment_lab.domain.errors import Conflict


def export_candidate(
    store: ResearchRepository, artifacts: ArtifactStore, iteration_id: str
) -> dict:
    iteration = store.iteration(iteration_id)
    if iteration["result"] is None:
        raise Conflict("Candidate has no replay evidence")
    study = store.study(iteration["study_id"])["config"]
    result = artifacts.get(iteration["result"]["artifact_id"])
    return {
        "schema_version": 1,
        "family": study["strategy_id"],
        "proposed_release_id": "lab-" + iteration_id,
        "runtime_version": result["runtime_version"],
        "runtime_hash": result["runtime_hash"],
        "interval": study["interval"],
        "symbol": "BTCUSDT",
        "parameters": iteration["parameters"],
        "dataset_id": study["dataset_id"],
        "evidence_artifact_id": iteration["result"]["artifact_id"],
        "metrics": iteration["result"]["metrics"],
        "exposure": "DEVELOPMENT_EXPOSED",
        "activation_allowed": False,
        "compatibility": "DEVELOPER_PARITY_REVIEW_REQUIRED"
        if study["interval"] == "4h"
        else "RUNTIME_SUPPORT_REQUIRED",
    }
