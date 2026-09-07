"""Local-only Lab acceptance stack. Synthetic provider is never shipped in images.

Run with backend/.venv/bin/python and repository-root cwd. Binds only loopback.
The disposable database name is guarded; no exchange credential is provisioned.
"""

import argparse
import asyncio
import base64
import os
import re
import logging

import httpx
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA_DATA = Path(
    os.environ.get("CP_QA_LAB_DATA_DIR", str(ROOT / ".lab-data/qa"))
).resolve()
if not QA_DATA.is_relative_to(ROOT / ".lab-data"):
    raise ValueError(
        "QA Lab data must stay inside the ignored local .lab-data directory"
    )
sys.path[:0] = [
    str(ROOT / "backend"),
    str(ROOT / "experiments/experiment_lab/src"),
    str(ROOT / "packages/strategy_runtime/src"),
]
QA_DATABASE = os.environ.get("CP_QA_DATABASE_NAME", "cryptopilot_lab_e2e")
if re.fullmatch(r"cryptopilot_[a-z0-9_]+_e2e", QA_DATABASE) is None:
    raise ValueError("QA database must have a disposable cryptopilot_*_e2e name")
os.environ.update(
    {
        "CP_DATABASE_URL": f"postgresql+asyncpg://labqa:labqa-test-only@127.0.0.1:55432/{QA_DATABASE}",
        "CP_MASTER_KEY": base64.b64encode(b"Q" * 32).decode(),
        "CP_JWT_SECRET": "qa-only-signing-key-" * 3,
        "CP_ENVIRONMENT": "test",
        "CP_OTP_TEST_MODE": "true",
        "CP_OTP_TEST_DISABLE_THROTTLE": "true",
        "CP_LIVE_TRADING_APPROVED": "false",
        "CP_LIVE_KEY_PERMISSIONS_VERIFIED": "false",
        "CP_FRONTEND_ORIGIN": "http://localhost:5173",
        "CP_CODEX_HOME": str(ROOT / ".lab-data/qa/codex-test"),
        "CP_LAB_URL": "http://127.0.0.1:8010",
        "CP_LAB_SERVICE_TOKEN": "lab-qa-service-only-" * 3,
        "LAB_SERVICE_TOKEN": "lab-qa-service-only-" * 3,
        "LAB_RUNNER_TOKEN": "lab-qa-runner-only-" * 3,
        "LAB_ADVISOR_TOKEN": "lab-qa-advisor-only-" * 3,
        "LAB_SERVICE_URL": "http://127.0.0.1:8010",
        "LAB_DATA_DIR": str(QA_DATA),
    }
)


class FixtureAdvisor:
    async def evaluate(self, kind, context):
        if kind == "SELECT":
            previous = next((row for row in context["history"] if row["result"]), None)
            parameters = dict(
                previous["parameters"]
                if previous
                else context["study"]["config"]["parameters"]
            )
            if "stop_atr" not in context["study"]["config"]["pinned"]:
                parameters["stop_atr"] = (
                    "2.6" if parameters["stop_atr"] == "2.5" else "2.5"
                )
            return {
                "parameters": parameters,
                "hypothesis": "QA fixture: compare a small stop-distance change.",
                "evidence_ids": [previous["id"]] if previous else [],
                "uncertainty": "Synthetic advisor; no model capability evidence.",
                "falsification": "Reject if risk-adjusted results deteriorate.",
            }
        return {
            "summary": "QA fixture reviewed the saved replay result.",
            "lesson": "Compare this result with the unchanged baseline; improvement is not guaranteed.",
            "counterevidence": "A single historical test does not establish robustness.",
            "next_hypothesis": "Revisit the baseline if the new setting performs worse.",
            "evidence_ids": [context["iteration"]["id"]],
        }


async def advise():
    from app.experiment_lab.advisor import run_once
    from app.experiment_lab.client import LabClient

    client = LabClient(os.environ["CP_LAB_URL"], os.environ["LAB_ADVISOR_TOKEN"])
    while True:
        try:
            for kind in ("SELECT", "REVIEW"):
                await run_once(client, FixtureAdvisor(), kind)
        except httpx.HTTPError as error:
            logging.warning("QA Lab unavailable: %s", type(error).__name__)
        await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["seed", "backend", "lab", "runner", "advisor", "download"]
    )
    args = parser.parse_args()
    if args.mode == "seed":
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            check=True,
        )
        from app.cli import _create_owner
        from app.e2e_seed import _main as seed_e2e

        async def provision():
            await _create_owner(
                "qa-owner@example.com", "PilotOwner!2026", "94711234567", False
            )
            await seed_e2e()

        asyncio.run(provision())
    elif args.mode == "backend":
        import uvicorn

        uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
    elif args.mode == "lab":
        import uvicorn

        uvicorn.run(
            "experiment_lab.api:create_app", factory=True, host="127.0.0.1", port=8010
        )
    elif args.mode == "runner":
        from experiment_lab.worker import main as worker

        worker()
    elif args.mode == "advisor":
        if not QA_DATA.is_relative_to(ROOT / ".lab-data/qa"):
            raise ValueError("Fixture advisor cannot write to real-advisor evidence")
        asyncio.run(advise())
    else:
        from datetime import datetime, timezone
        from experiment_lab.adapters.artifacts import Artifacts
        from experiment_lab.adapters.binance import BinanceData
        from experiment_lab.settings import Settings

        settings = Settings()
        identity = BinanceData(Artifacts(settings.data_dir / "artifacts")).download(
            datetime(2023, 9, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 1, tzinfo=timezone.utc),
            "4h",
        )
        print("Actual Binance three-year dataset:", identity)


if __name__ == "__main__":
    main()
