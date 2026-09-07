"""Run the complete local QA stack in one supervised foreground session.

Seed with lab_stack.py first. Existing listeners cause startup to fail rather than
replacing unrelated services. Ctrl-C stops only this supervisor's child groups.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    for port in (5173, 8000, 8010):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise SystemExit(
                    f"Port {port} is already in use; existing services were preserved."
                ) from error
    processes: list[subprocess.Popen] = []
    commands = [
        ([sys.executable, str(ROOT / "qa/fixtures/lab_stack.py"), mode], ROOT)
        for mode in ("lab", "runner", "advisor", "backend")
    ] + [(["npm", "run", "dev", "--", "--host", "127.0.0.1"], ROOT / "frontend")]
    environment = os.environ | {
        "VITE_DEV_API_PROXY": "http://127.0.0.1:8000",
        "VITE_EXPERIMENT_LAB_ENABLED": "true",
    }
    try:
        for command, directory in commands:
            processes.append(
                subprocess.Popen(
                    command, cwd=directory, env=environment, start_new_session=True
                )
            )
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        raise SystemExit(
            "A QA service exited; stopping this stack to avoid an incomplete Lab."
        )
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == "__main__":
    main()
