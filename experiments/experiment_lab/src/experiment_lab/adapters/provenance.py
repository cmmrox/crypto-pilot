"""Content identity includes the actual runtime bytes, including research edits."""

import hashlib
from importlib.metadata import version
from pathlib import Path

import strategy_runtime


def runtime_hash() -> str:
    root = Path(strategy_runtime.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluator_hash() -> str:
    """Pin replay, data validation and policy bytes plus numerical dependencies."""
    root = Path(__file__).parent.parent
    digest = hashlib.sha256(runtime_hash().encode())
    for relative in (
        "adapters/replay.py",
        "adapters/binance.py",
        "adapters/trade_archive.py",
        "domain/policy.py",
    ):
        digest.update(relative.encode())
        digest.update((root / relative).read_bytes())
    for distribution in ("numpy", "pandas", "pydantic"):
        digest.update(f"{distribution}=={version(distribution)}".encode())
    return digest.hexdigest()
