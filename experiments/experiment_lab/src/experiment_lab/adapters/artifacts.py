"""Content-addressed artifacts: bytes become durable before metadata references them."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Artifacts:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, value: object) -> str:
        data = canonical(value).encode()
        digest = hashlib.sha256(data).hexdigest()
        target = self.root / f"{digest}.json"
        if target.exists():
            self.get(digest)  # Never silently reuse a corrupted immutable artifact.
            return digest
        temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as output:
                temp = Path(output.name)
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, target)
            fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        return digest

    # JSON artifacts have several schemas; their consumers validate the selected schema.
    def get(self, digest: str) -> Any:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid artifact ID")
        data = (self.root / f"{digest}.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Artifact integrity check failed")
        return json.loads(data)
