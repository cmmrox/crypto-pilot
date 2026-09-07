"""Private service HTTP boundary. Owner authorization lives in the application BFF."""

from dataclasses import asdict
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from strategy_runtime.parameters import DEFINITIONS

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.binance import validate_dataset
from experiment_lab.adapters.provenance import evaluator_hash, runtime_hash
from experiment_lab.adapters.store import SCHEMA_VERSION, Conflict, Store
from experiment_lab.application.service import LabService
from experiment_lab.domain.models import (
    Completion,
    Failure,
    IterationInput,
    LeaseRequest,
    LeaseToken,
    StudyInput,
)
from experiment_lab.settings import Settings
from experiment_lab.http_limits import RequestLimit


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    artifacts = Artifacts(config.data_dir / "artifacts")
    store = Store(config.data_dir / "lab.sqlite3")
    service = LabService(
        store, artifacts, runtime_hash, validate_dataset, evaluator_hash
    )

    def authenticate(
        request: Request, authorization: Annotated[str, Header()] = ""
    ) -> str:
        for role, credential in (
            ("OWNER", config.service_token),
            ("ADVISOR", config.advisor_token),
            ("RUNNER", config.runner_token),
        ):
            if credential is not None and compare_digest(
                authorization.encode(),
                ("Bearer " + credential.get_secret_value()).encode(),
            ):
                if (
                    role != "OWNER"
                    and request.method != "GET"
                    and not request.url.path.startswith("/jobs/")
                ):
                    raise HTTPException(403, "Owner credential required")
                return role
        raise HTTPException(401, "Invalid service credential")

    def authorize_job(kind: str, role: str) -> None:
        expected = "RUNNER" if kind == "REPLAY" else "ADVISOR"
        if role != expected:
            raise HTTPException(403, "Credential does not authorize this worker stage")

    app = FastAPI(
        title="CryptoPilot Experiment Lab",
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
        dependencies=[Depends(authenticate)],
    )
    app.add_middleware(RequestLimit)
    app.state.service = service

    @app.exception_handler(Conflict)
    async def conflict(_request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(ValueError)
    async def invalid(_request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)[:500]})

    @app.exception_handler(KeyError)
    @app.exception_handler(FileNotFoundError)
    async def missing(_request, _error):
        return JSONResponse(status_code=404, content={"detail": "Resource not found"})

    @app.get("/health")
    def health():
        with store.connection() as db:
            db.execute("SELECT 1 FROM studies LIMIT 1").fetchone()
        return {"status": "ok", "schema_version": SCHEMA_VERSION}

    @app.get("/strategies")
    def strategies():
        return [
            {
                "id": "trend_rider_v6_4h",
                "name": "Trend Rider v6",
                "intervals": ["4h", "1h", "30m"],
                "parameters": [asdict(item) for item in DEFINITIONS],
            }
        ]

    @app.get("/studies")
    def studies(
        before_id: Annotated[str | None, Query(pattern=r"^[a-f0-9]{32}$")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return store.studies(before_id, limit)

    @app.post("/studies", status_code=201)
    def create_study(request: StudyInput):
        return service.create_study(request)

    @app.get("/studies/{study_id}")
    def study(
        study_id: str,
        before: Annotated[int | None, Query(ge=1)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ):
        return (
            store.study(study_id)
            | store.summary(study_id)
            | store.iteration_page(study_id, before, limit)
        )

    @app.post("/studies/{study_id}/iterations", status_code=202)
    def start(
        study_id: str,
        request: IterationInput,
        idempotency_key: Annotated[str, Header()],
    ):
        return service.start(study_id, request, idempotency_key)

    @app.post("/iterations/{iteration_id}/cancel", status_code=204)
    def cancel(iteration_id: str):
        store.iteration(iteration_id)
        store.cancel(iteration_id)
        return Response(status_code=204)

    @app.get("/iterations/{iteration_id}/artifact")
    def artifact(iteration_id: str):
        iteration = store.iteration(iteration_id)
        if not iteration["result"]:
            raise HTTPException(409, "Replay has not completed")
        return artifacts.get(iteration["result"]["artifact_id"])

    @app.post("/iterations/{iteration_id}/retry-review", status_code=202)
    def retry_review(iteration_id: str):
        store.retry_review(iteration_id)
        return store.iteration(iteration_id)

    @app.get("/iterations/{iteration_id}/candidate")
    def candidate(iteration_id: str):
        from experiment_lab.application.candidate import export_candidate

        return export_candidate(store, artifacts, iteration_id)

    @app.get("/studies/{study_id}/skill")
    def skill(study_id: str):
        from experiment_lab.application.service import METHODOLOGY

        study = store.study(study_id)
        lessons = store.lessons(study_id, limit=20)
        markdown = f"# {study['config']['name']} research skill\n\n{METHODOLOGY}\nShowing the latest 20 revisions; older evidence remains in iteration history.\n"
        for lesson in lessons:
            markdown += f"\n## Revision {lesson['revision']} — {lesson['status']}\n{lesson['content']['lesson']}\n\nCounterevidence: {lesson['content']['counterevidence']}\n"
        return {
            "methodology_version": 1,
            "revision": lessons[-1]["revision"] if lessons else 0,
            "markdown": markdown,
            "lessons": lessons,
        }

    @app.post("/jobs/claim")
    def claim(request: LeaseRequest, role: str = Depends(authenticate)):
        authorize_job(request.kind, role)
        job = store.claim(request.kind)
        return (
            None
            if job is None
            else job | {"context": service.context(job["iteration_id"])}
        )

    @app.post("/jobs/{job_id}/heartbeat", status_code=204)
    def heartbeat(job_id: str, request: LeaseToken, role: str = Depends(authenticate)):
        authorize_job(store.job(job_id, request.lease_token)["kind"], role)
        store.heartbeat(job_id, request.lease_token)
        return Response(status_code=204)

    @app.post("/jobs/{job_id}/complete")
    def complete(job_id: str, request: Completion, role: str = Depends(authenticate)):
        authorize_job(store.job(job_id, request.lease_token)["kind"], role)
        return service.complete(job_id, request.lease_token, request.output)

    @app.post("/jobs/{job_id}/fail", status_code=204)
    def fail(job_id: str, request: Failure, role: str = Depends(authenticate)):
        authorize_job(store.job(job_id, request.lease_token)["kind"], role)
        store.fail(job_id, request.lease_token, request.error_code)
        return Response(status_code=204)

    return app
