"""Explicitly authorized, bounded QA batch; every iteration uses the real advisor.

This is a local experiment operator, not an automatic live-trading optimizer.
Stops on the first failed stage; completed evidence is retained by the Lab API.
"""

import argparse
import asyncio
import json
import time
import uuid

import lab_stack  # Establish the existing local-only QA client configuration.


async def run(study_id: str, count: int, codex_home: str) -> None:
    from app.experiment_lab.advisor import AdvisorSettings, CodexAdvisor, run_once
    from app.experiment_lab.client import LabClient

    owner = LabClient(
        "http://127.0.0.1:8010", lab_stack.os.environ["LAB_SERVICE_TOKEN"]
    )
    advisor_client = LabClient(
        "http://127.0.0.1:8010", lab_stack.os.environ["LAB_ADVISOR_TOKEN"]
    )
    advisor = CodexAdvisor(
        AdvisorSettings(
            lab_url=advisor_client.url,
            lab_service_token=advisor_client.token,
            codex_home=codex_home,
        )
    )
    batch_id = uuid.uuid4().hex
    study = await owner.request("GET", f"/studies/{study_id}")
    if any(
        row["status"] not in {"COMPLETED", "FAILED", "CANCELLED"}
        for row in study["iterations"]
    ):
        raise ValueError("Study already has an active iteration")
    print(
        json.dumps({"batch_id": batch_id, "requested": count, "study_id": study_id}),
        flush=True,
    )
    for index in range(count):
        iteration = await owner.request(
            "POST",
            f"/studies/{study_id}/iterations",
            body={"mode": "ADVISED"},
            key=f"batch-{batch_id}-{index}",
        )
        deadline = time.monotonic() + 900
        previous_status = None
        while time.monotonic() < deadline:
            detail = await owner.request("GET", f"/studies/{study_id}")
            current = next(
                row for row in detail["iterations"] if row["id"] == iteration["id"]
            )
            if current["status"] != previous_status:
                print(
                    json.dumps(
                        {
                            "batch_completed": index,
                            "ordinal": current["ordinal"],
                            "status": current["status"],
                        }
                    ),
                    flush=True,
                )
                previous_status = current["status"]
            if current["status"] == "COMPLETED":
                metrics = current["result"]["metrics"]
                print(
                    json.dumps(
                        {
                            "batch_completed": index + 1,
                            "ordinal": current["ordinal"],
                            "metrics": {
                                key: metrics[key]
                                for key in (
                                    "net_profit",
                                    "max_drawdown",
                                    "worst_month",
                                    "profitable_month_ratio",
                                    "profit_factor",
                                    "trade_count",
                                )
                            },
                        }
                    ),
                    flush=True,
                )
                break
            if current["status"] in {"FAILED", "CANCELLED"}:
                raise RuntimeError(
                    f"Batch stopped at iteration {current['id']}: {current['status']}"
                )
            for kind in ("SELECT", "REVIEW"):
                await run_once(advisor_client, advisor, kind)
            await asyncio.sleep(2)
        else:
            raise TimeoutError(
                f"Iteration {iteration['id']} exceeded the batch time bound"
            )
    print(
        json.dumps({"batch_id": batch_id, "completed": count, "status": "FINISHED"}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--count", type=int, choices=range(1, 51), required=True)
    parser.add_argument("--codex-home", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.study, args.count, args.codex_home))
