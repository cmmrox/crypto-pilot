"""One workflow coordinator; adapters do not decide research policy."""

from dataclasses import asdict
from collections.abc import Callable

from strategy_runtime.parameters import DEFINITIONS, validate_parameters

from experiment_lab.application.ports import ArtifactStore, ResearchRepository
from experiment_lab.domain.errors import Conflict
from experiment_lab.domain.models import Advice, IterationInput, Review, StudyInput

METHODOLOGY = """Compare like-for-like periods and initial capital. All previously seen data is development exposed.
Improve risk-adjusted monthly consistency, not just maximum in-sample profit. Never promise profitable months.
Change at most three unpinned parameters per run. Cite earlier iteration IDs, test one explicit hypothesis,
state uncertainty and falsification. Failed hypotheses are evidence too. An exact repeat is not independent
replication. Do not change code, dates, leverage bounds, risk policy, data or trading state. Evaluate input
and output together, keep counterevidence, and distinguish observation from causal evidence.
"""


class LabService:
    def __init__(
        self,
        store: ResearchRepository,
        artifacts: ArtifactStore,
        runtime_identity: Callable[[], str],
        verify_dataset: Callable[[dict], None],
        evaluator_identity: Callable[[], str] | None = None,
    ):
        self.store = store
        self.artifacts = artifacts
        self.runtime_identity = runtime_identity
        self.verify_dataset = verify_dataset
        self.evaluator_identity = evaluator_identity

    def create_study(self, request: StudyInput) -> dict:
        config = request.model_dump(mode="json")
        config["runtime_hash"] = self.runtime_identity()
        if self.evaluator_identity is not None:
            config["evaluator_hash"] = self.evaluator_identity()
        dataset = self.artifacts.get(request.dataset_id)
        self.verify_dataset(dataset)
        from datetime import datetime

        if (
            dataset["interval"] != request.interval
            or request.start < datetime.fromisoformat(dataset["start"])
            or request.end > datetime.fromisoformat(dataset["end"])
        ):
            raise ValueError("Study is outside the verified dataset window")
        return self.store.create_study(config)

    def start(self, study_id: str, request: IterationInput, key: str) -> dict:
        study = self.store.study(study_id)["config"]
        if study.get("runtime_hash") != self.runtime_identity():
            raise Conflict(
                "Strategy runtime changed; create a new study to preserve comparison integrity"
            )
        if (
            self.evaluator_identity is not None
            and study.get("evaluator_hash") != self.evaluator_identity()
        ):
            raise Conflict(
                "Replay evaluator changed; create a new study to preserve comparison integrity"
            )
        if not 8 <= len(key) <= 100:
            raise ValueError("Supply an 8–100 character idempotency key")
        parameters = study["parameters"]
        if request.mode == "MANUAL":
            parameters = validate_parameters(request.parameters)
        elif request.mode == "REPRODUCE":
            source = self.store.iteration(request.source_iteration_id or "")
            if source["study_id"] != study_id or not source["result"]:
                raise ValueError("Reproduction requires a result from this study")
            parameters = source["parameters"]
        elif request.parameters or request.source_iteration_id:
            raise ValueError(
                "Advised runs select parameters from evidence, not hidden overrides"
            )
        return self.store.create_iteration(
            study_id, key, request.model_dump(mode="json"), parameters
        )

    def context(self, iteration_id: str) -> dict:
        iteration = self.store.iteration(iteration_id)
        study = self.store.study(iteration["study_id"])
        self.store.expose(study["id"], study["config"])
        return {
            "study": study,
            "iteration": iteration,
            **self.store.history_context(study["id"], before=iteration["ordinal"]),
            "lessons": self.store.lessons(study["id"], limit=20),
            "strategy_lessons": self.store.strategy_lessons(
                study["config"]["strategy_id"]
            ),
            "methodology": METHODOLOGY,
            "parameter_definitions": [asdict(item) for item in DEFINITIONS],
            "exposure": "DEVELOPMENT_EXPOSED",
        }

    def complete(self, job_id: str, token: str, output: dict) -> dict:
        job = self.store.job(job_id, token)
        context = self.context(job["iteration_id"])
        if job["kind"] == "SELECT":
            advice = Advice.model_validate(output)
            values = validate_parameters(advice.parameters)
            seed = context["study"]["config"]["parameters"]
            if set(advice.parameters) != set(seed):
                raise ValueError("Advice must specify the complete parameter set")
            for key in context["study"]["config"]["pinned"]:
                if values[key] != seed[key]:
                    raise ValueError(f"Advisor changed pinned parameter {key}")
            previous = next(
                (row["parameters"] for row in context["history"] if row["result"]), seed
            )
            if sum(values[key] != previous[key] for key in values) > 3:
                raise ValueError(
                    "Change no more than three parameters in one hypothesis"
                )
            valid_ids = {row["id"] for row in context["history"]} | {
                row["iteration_id"] for row in context["strategy_lessons"]
            }
            if not set(advice.evidence_ids) <= valid_ids:
                raise ValueError("Advice cites unknown evidence")
            output = advice.model_dump() | {"parameters": values}
        elif job["kind"] == "REVIEW":
            review = Review.model_validate(output)
            valid_ids = (
                {row["id"] for row in context["history"]}
                | {job["iteration_id"]}
                | {row["iteration_id"] for row in context["strategy_lessons"]}
            )
            if (
                not set(review.evidence_ids) <= valid_ids
                or job["iteration_id"] not in review.evidence_ids
            ):
                raise ValueError(
                    "Review must cite the current iteration and only real evidence"
                )
            output = review.model_dump()
        else:
            artifact = self.artifacts.get(output["artifact_id"])
            if (
                artifact["parameters"] != context["iteration"]["parameters"]
                or artifact["study"] != context["study"]["config"]
                or artifact["metrics"] != output["metrics"]
            ):
                raise ValueError("Replay artifact does not match its run")
            if context["iteration"]["mode"] == "REPRODUCE":
                source = self.store.iteration(
                    context["iteration"]["request"]["source_iteration_id"]
                )
                if output["metrics"] != source["result"]["metrics"]:
                    raise ValueError(
                        "Reproduction differs from its immutable source result"
                    )
        record_id = self.artifacts.put(
            {"job_id": job_id, "context": context, "output": output}
        )
        output = output | {"decision_record_id": record_id}
        identity = self.store.finish(job_id, token, output)
        return self.store.iteration(identity)
