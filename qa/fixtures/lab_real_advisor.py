"""Bounded real-Codex acceptance against an isolated, durable Lab store.

Uses actual Binance data, production HTTP handlers and the application advisor.
ASGI transport avoids connecting to any existing bot or fixture-advisor process.
Each explicitly requested cycle is started once; failures stop the run. No orders.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "backend"),
    str(ROOT / "experiments/experiment_lab/src"),
    str(ROOT / "packages/strategy_runtime/src"),
]


async def exercise(dataset_path: Path, codex_home: Path, cycles: int) -> None:
    import secrets

    from app.experiment_lab.advisor import AdvisorSettings, CodexAdvisor
    from experiment_lab.adapters.artifacts import Artifacts
    from experiment_lab.adapters.replay import Replay
    from experiment_lab.api import create_app
    from experiment_lab.settings import Settings

    data = json.loads(dataset_path.read_text())
    if data.get("source") != "BINANCE_USDM_PUBLIC" or data.get("test_fixture"):
        raise ValueError("Actual Binance data is required")
    directory = ROOT / ".lab-data" / "real-advisor" / uuid.uuid4().hex
    artifacts = Artifacts(directory / "artifacts")
    dataset_id = artifacts.put(data)
    if dataset_id != dataset_path.stem:
        raise ValueError("Dataset identity mismatch")
    owner, advisor_token, runner = (secrets.token_urlsafe(32) for _ in range(3))
    app = create_app(
        Settings(
            data_dir=directory,
            service_token=owner,
            advisor_token=advisor_token,
            runner_token=runner,
        )
    )
    advisor = CodexAdvisor(
        AdvisorSettings(
            lab_url="http://lab-qa",
            lab_service_token=advisor_token,
            codex_home=str(codex_home),
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://lab-qa"
    ) as client:

        async def request(method, path, body=None, token=owner, key=None):
            headers = {"Authorization": f"Bearer {token}"}
            if key:
                headers["Idempotency-Key"] = key
            response = await client.request(method, path, json=body, headers=headers)
            if response.is_error:
                # Response is the Lab's bounded public validation message, not provider stderr.
                raise RuntimeError(
                    f"{path}: {response.status_code} {response.text[:500]}"
                )
            return response.json()

        study = await request(
            "POST",
            "/studies",
            {
                "name": "Real Codex QA: three-year controlled learning",
                "dataset_id": dataset_id,
                "start": data["start"],
                "end": data["end"],
                "interval": data["interval"],
                "initial_capital": "100",
            },
        )
        print(f"Evidence directory: {directory}\nStudy: {study['id']}", flush=True)
        for index in range(cycles):
            iteration = await request(
                "POST",
                f"/studies/{study['id']}/iterations",
                {"mode": "ADVISED"},
                key=f"real-cycle-{index + 1}",
            )
            for kind in (
                ["REPLAY", "REVIEW"] if index == 0 else ["SELECT", "REPLAY", "REVIEW"]
            ):
                token = runner if kind == "REPLAY" else advisor_token
                job = await request("POST", "/jobs/claim", {"kind": kind}, token)
                assert job and job["iteration_id"] == iteration["id"]
                print(
                    f"Cycle {index + 1}: {kind}; prior lessons={len(job['context']['lessons'])}",
                    flush=True,
                )
                try:
                    if kind == "REPLAY":
                        output = await asyncio.to_thread(
                            Replay(artifacts).run, job["context"]
                        )
                    else:
                        output = await advisor.evaluate(kind, job["context"])
                    await request(
                        "POST",
                        f"/jobs/{job['id']}/complete",
                        {"lease_token": job["token"], "output": output},
                        token,
                    )
                except Exception:
                    await request(
                        "POST",
                        f"/jobs/{job['id']}/fail",
                        {"lease_token": job["token"]},
                        token,
                    )
                    raise
            detail = await request("GET", f"/studies/{study['id']}")
            current = next(
                row for row in detail["iterations"] if row["id"] == iteration["id"]
            )
            assert current["status"] == "COMPLETED"
            skill = await request("GET", f"/studies/{study['id']}/skill")
            assert skill["revision"] == index + 1
            metrics = current["result"]["metrics"]
            print(
                json.dumps(
                    {
                        "cycle": index + 1,
                        "id": current["id"],
                        "parameters": current["parameters"],
                        "metrics": {
                            key: metrics[key]
                            for key in (
                                "net_profit",
                                "final_equity",
                                "max_drawdown",
                                "worst_month",
                                "profitable_month_ratio",
                                "profit_factor",
                                "trade_count",
                                "stressed_net_profit",
                                "suitable_for_live",
                            )
                        },
                    }
                ),
                flush=True,
            )
        for kind, token in (
            ("SELECT", advisor_token),
            ("REPLAY", runner),
            ("REVIEW", advisor_token),
        ):
            assert await request("POST", "/jobs/claim", {"kind": kind}, token) is None
        print(
            "PASS: requested real-model cycles completed, lessons persisted, no automatic next run.",
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--cycles", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    asyncio.run(
        exercise(args.dataset.resolve(), args.codex_home.resolve(), args.cycles)
    )
