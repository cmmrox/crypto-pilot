"""Disposable container acceptance: no exchange keys, real orders or host credentials.

Run with backend/.venv/bin/python and an existing public Binance dataset artifact.
Only this invocation's UUID-named containers, network and volume are removed.
"""

import argparse
import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path

import httpx


def docker(*arguments: str, required: bool = True) -> str:
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    if required and result.returncode:
        # Never render Docker command arguments: environment flags may be credentials.
        raise RuntimeError(f"Docker {arguments[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def wait_until(check, description: str, timeout: int = 120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise TimeoutError(description)


def exercise(dataset_path: Path) -> None:
    dataset = json.loads(dataset_path.read_text())
    if dataset.get("source") != "BINANCE_USDM_PUBLIC" or dataset.get("test_fixture"):
        raise ValueError("This smoke test requires the actual public Binance dataset")
    identity = "cp-lab-smoke-" + uuid.uuid4().hex[:12]
    api_name, runner_name = identity + "-api", identity + "-runner"
    volume, network = identity + "-data", identity + "-net"
    owner, advisor, runner = (secrets.token_urlsafe(32) for _ in range(3))
    try:
        # Docker Desktop does not publish host ports on an internal network.
        # Use a dedicated bridge with a loopback-only published API instead.
        docker("network", "create", network)
        docker("volume", "create", volume)
        docker(
            "run",
            "-d",
            "--name",
            api_name,
            "--network",
            network,
            "--read-only",
            "--tmpfs",
            "/tmp:size=128m,mode=1777",
            "--pids-limit",
            "128",
            "--memory",
            "512m",
            "--cpus",
            "0.5",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "-p",
            "127.0.0.1::8010",
            "-v",
            f"{volume}:/data",
            "-e",
            "LAB_DATA_DIR=/data",
            "-e",
            f"LAB_SERVICE_TOKEN={owner}",
            "-e",
            f"LAB_ADVISOR_TOKEN={advisor}",
            "-e",
            f"LAB_RUNNER_TOKEN={runner}",
            "cryptopilot-experiment-lab:qa",
        )
        port = json.loads(docker("inspect", api_name))[0]["NetworkSettings"]["Ports"][
            "8010/tcp"
        ][0]["HostPort"]
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers={"Authorization": f"Bearer {owner}"},
            timeout=15,
        ) as client:
            wait_until(
                lambda: client.get("/health").status_code == 200,
                "Lab API did not become healthy",
            )
            assert (
                client.get("/health", headers={"Authorization": ""}).status_code == 401
            )
            assert (
                client.post("/jobs/claim", json={"kind": "SELECT"}).status_code == 403
            )
            assert (
                client.post(
                    "/studies", json={}, headers={"Authorization": f"Bearer {runner}"}
                ).status_code
                == 403
            )
            # Ingest public bytes through the actual artifact adapter as the Lab UID.
            # This retains cap-drop ALL and avoids host ownership on private artifacts.
            ingest = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    api_name,
                    "python",
                    "-c",
                    "import json,sys; from pathlib import Path; "
                    "from experiment_lab.adapters.artifacts import Artifacts; "
                    "print(Artifacts(Path('/data/artifacts')).put(json.load(sys.stdin)))",
                ],
                input=dataset_path.read_bytes(),
                capture_output=True,
                check=True,
            )
            assert ingest.stdout.decode().strip() == dataset_path.stem
            response = client.post(
                "/studies",
                json={
                    "name": "Container QA: real Binance, fixture review",
                    "dataset_id": dataset_path.stem,
                    "start": "2026-08-01T00:00:00Z",
                    "end": "2026-09-01T00:00:00Z",
                    "interval": "4h",
                    "pinned": ["risk_pct"],
                },
            )
            response.raise_for_status()
            study = response.json()["id"]
            docker(
                "run",
                "-d",
                "--name",
                runner_name,
                "--network",
                network,
                "--read-only",
                "--tmpfs",
                "/tmp:size=128m,mode=1777",
                "--pids-limit",
                "128",
                "--memory",
                "1g",
                "--cpus",
                "1",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-v",
                f"{volume}:/data",
                "-e",
                "LAB_DATA_DIR=/data",
                "-e",
                f"LAB_SERVICE_TOKEN={runner}",
                "-e",
                f"LAB_SERVICE_URL=http://{api_name}:8010",
                "cryptopilot-experiment-lab:qa",
                "python",
                "-m",
                "experiment_lab.worker",
            )

            def start(body, key):
                response = client.post(
                    f"/studies/{study}/iterations",
                    json=body,
                    headers={"Idempotency-Key": key},
                )
                response.raise_for_status()
                return response.json()

            def complete_review():
                def claim():
                    response = client.post(
                        "/jobs/claim",
                        json={"kind": "REVIEW"},
                        headers={"Authorization": f"Bearer {advisor}"},
                    )
                    response.raise_for_status()
                    return response.json()

                job = wait_until(claim, "Container replay did not reach review")
                response = client.post(
                    f"/jobs/{job['id']}/complete",
                    headers={"Authorization": f"Bearer {advisor}"},
                    json={
                        "lease_token": job["token"],
                        "output": {
                            "summary": "Container QA fixture review; not real model evaluation.",
                            "lesson": "A replay result alone cannot certify live trading.",
                            "counterevidence": "No untouched holdout was evaluated.",
                            "next_hypothesis": "Compare the next controlled parameter change.",
                            "evidence_ids": [job["iteration_id"]],
                        },
                    },
                )
                response.raise_for_status()
                return response.json()

            first = start({"mode": "ADVISED"}, "container-baseline")
            assert start({"mode": "ADVISED"}, "container-baseline")["id"] == first["id"]
            baseline = complete_review()
            assert baseline["status"] == "COMPLETED"
            docker("restart", api_name)
            # Docker can assign a different ephemeral host port after restart.
            port = json.loads(docker("inspect", api_name))[0]["NetworkSettings"][
                "Ports"
            ]["8010/tcp"][0]["HostPort"]
            client.base_url = f"http://127.0.0.1:{port}"
            wait_until(
                lambda: client.get("/health").status_code == 200, "API restart failed"
            )
            assert (
                client.get(f"/studies/{study}").json()["iterations"][0]["id"]
                == baseline["id"]
            )
            start(
                {"mode": "REPRODUCE", "source_iteration_id": baseline["id"]},
                "container-reproduce",
            )
            repeated = complete_review()
            assert repeated["result"]["metrics"] == baseline["result"]["metrics"]
            assert repeated["status"] == "COMPLETED"
            assert len(client.get(f"/studies/{study}/skill").json()["lessons"]) == 2
            image_probe = docker(
                "exec",
                api_name,
                "python",
                "-c",
                "import importlib.util,os; assert os.getuid()!=0; assert importlib.util.find_spec('app') is None; print('isolated')",
            )
            assert image_probe == "isolated"
            print(
                "PASS: container auth scopes, real-data replay, idempotency, restart persistence, exact reproduction, non-root app isolation",
                flush=True,
            )
    finally:
        for container in (runner_name, api_name):
            docker("rm", "-f", container, required=False)
        docker("volume", "rm", volume, required=False)
        docker("network", "rm", network, required=False)
        print(
            "Disposable smoke-test containers, data volume and network cleaned up; existing QA data preserved.",
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    exercise(parser.parse_args().dataset.resolve())
