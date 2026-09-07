"""Supervised replay subprocess; only the API process writes workflow SQLite."""

import contextlib
import logging
import multiprocessing
import time
from pathlib import Path

import httpx

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.replay import Replay
from experiment_lab.settings import Settings
from experiment_lab.domain.failures import failure_code

log = logging.getLogger("experiment_lab.worker")


def replay_child(root: str, context: dict, sender) -> None:
    """Only artifacts and a bounded result cross the process boundary."""
    try:
        result = Replay(Artifacts(Path(root) / "artifacts")).run(context)
        sender.send({"ok": True, "output": result})
    except Exception as error:
        sender.send(
            {
                "ok": False,
                "error_type": type(error).__name__,
                "error_code": failure_code(error),
            }
        )
    finally:
        sender.close()


def run_once(client: httpx.Client, config: Settings) -> bool:
    response = client.post("/jobs/claim", json={"kind": "REPLAY"})
    response.raise_for_status()
    job = response.json()
    if job is None:
        return False
    process_context = multiprocessing.get_context("spawn")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=replay_child, args=(str(config.data_dir), job["context"], sender)
    )
    process.start()
    sender.close()
    lease = {"lease_token": job["token"]}
    started = time.monotonic()
    public_failure = "WORKER_FAILED"
    log.info("replay_started job_id=%s iteration_id=%s", job["id"], job["iteration_id"])
    try:
        while not receiver.poll(10):
            if not process.is_alive():
                raise RuntimeError("Replay process exited without a result")
            if time.monotonic() - started > config.replay_timeout_seconds:
                raise TimeoutError("Replay exceeded its configured execution budget")
            response = client.post(f"/jobs/{job['id']}/heartbeat", json=lease)
            response.raise_for_status()  # cancellation/stale lease terminates child
        result = receiver.recv()
        if not result["ok"]:
            public_failure = result["error_code"]
            log.error(
                "replay_child_failed job_id=%s cause_type=%s",
                job["id"],
                result["error_type"],
            )
            raise RuntimeError(result["error_type"])
        response = client.post(
            f"/jobs/{job['id']}/complete", json=lease | {"output": result["output"]}
        )
        response.raise_for_status()
        log.info(
            "replay_completed job_id=%s duration_s=%.3f",
            job["id"],
            time.monotonic() - started,
        )
    except Exception as error:
        if isinstance(error, TimeoutError):
            public_failure = failure_code(error)
        log.error(
            "replay_failed job_id=%s error_type=%s", job["id"], type(error).__name__
        )
        with contextlib.suppress(httpx.HTTPError):
            client.post(
                f"/jobs/{job['id']}/fail", json=lease | {"error_code": public_failure}
            ).raise_for_status()
    finally:
        receiver.close()
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = Settings()
    worker_token = config.runner_token or config.service_token
    with httpx.Client(
        base_url=config.service_url,
        headers={"Authorization": "Bearer " + worker_token.get_secret_value()},
        timeout=30,
    ) as client:
        while True:
            try:
                if not run_once(client, config):
                    time.sleep(2)
            except httpx.HTTPError as error:
                log.warning("lab_unavailable error_type=%s", type(error).__name__)
                time.sleep(5)


if __name__ == "__main__":
    main()
