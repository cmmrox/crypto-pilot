"""Synthetic volume probe: measures read amplification, not trading performance."""

import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from experiment_lab.adapters.store import Store


def measure(operation):
    tracemalloc.start()
    started = time.perf_counter()
    value = operation()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "milliseconds": round(elapsed * 1000, 2),
        "peak_bytes": peak,
        "result_count": len(value),
    }


def main():
    with tempfile.TemporaryDirectory(prefix="lab-volume-") as directory:
        store = Store(Path(directory) / "lab.sqlite3")
        study = store.create_study({"name": "Synthetic benchmark"})
        result = json.dumps(
            {
                "metrics": {
                    "net_profit": "0.00000001",
                    "monthly": [
                        {
                            "month": f"2024-{index:02}",
                            "profit": "100.12345678",
                            "return": "0.01",
                        }
                        for index in range(1, 37)
                    ],
                }
            }
        )
        with store.transaction() as db:
            db.executemany(
                "INSERT INTO iterations (id,study_id,ordinal,mode,status,request_key,request,parameters,result,created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    (
                        f"{i:032x}",
                        study["id"],
                        i,
                        "ADVISED",
                        "COMPLETED",
                        str(i),
                        "{}",
                        "{}",
                        result,
                        i,
                    )
                    for i in range(1, 10001)
                ),
            )
        evidence = {
            "synthetic": True,
            "iterations": 10000,
            "full_history": measure(lambda: store.iterations(study["id"])),
            "history_page": measure(
                lambda: store.iteration_page(study["id"], limit=20)["iterations"]
            ),
            "advisor_context": measure(
                lambda: store.history_context(study["id"], before=10001)["history"]
            ),
        }
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
