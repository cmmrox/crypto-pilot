"""Verified local snapshots; off-host copies still require operator encryption.

SQLite's online backup includes committed WAL pages. Immutable artifacts are copied
only after the database snapshot, so every referenced object already exists. Restore
publishes to a new directory and never overwrites an existing research store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(root: Path) -> None:
    manifest = json.loads((root / "backup-manifest.json").read_text())
    if manifest.get("version") != 1:
        raise ValueError("Unsupported backup manifest")
    paths = list(root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("Backup manifest cannot include symbolic links")
    actual = {str(path.relative_to(root)) for path in paths if path.is_file()}
    if actual != set(manifest["files"]) | {"backup-manifest.json"}:
        raise ValueError("Backup files do not match the manifest")
    for relative, digest in manifest["files"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("Backup contains an unsafe path")
        if file_hash(path) != digest:
            raise ValueError("Backup integrity check failed")
    with sqlite3.connect(
        f"file:{root / 'lab.sqlite3'}?mode=ro&immutable=1", uri=True
    ) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign key integrity check failed")
        # A valid SQLite file is not recoverable if a referenced immutable object
        # was already missing when the snapshot was taken. Stream references.
        queries = (
            "SELECT json_extract(config, '$.dataset_id') FROM studies",
            "SELECT json_extract(result, '$.artifact_id') FROM iterations",
            "SELECT json_extract(result, '$.decision_record_id') FROM iterations",
        )
        for query in queries:
            for (digest,) in db.execute(query):
                if (
                    digest is not None
                    and f"artifacts/{digest}.json" not in manifest["files"]
                ):
                    raise ValueError("Backup is missing a referenced artifact")


def publish(staging: Path, destination: Path) -> None:
    """Flush the snapshot before making its directory visible to the operator."""
    for path in staging.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    os.rename(staging, destination)
    descriptor = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def backup(source: Path, destination: Path) -> None:
    source, destination = source.resolve(), destination.absolute()
    if destination.exists():
        raise FileExistsError("Backup destination already exists")
    if destination.resolve().is_relative_to(source):
        raise ValueError("Backup destination must be outside the data directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=destination.parent, prefix=".lab-backup-"
    ) as directory:
        staging = Path(directory) / "snapshot"
        staging.mkdir(mode=0o700)
        with sqlite3.connect(f"file:{source / 'lab.sqlite3'}?mode=ro", uri=True) as db:
            with sqlite3.connect(staging / "lab.sqlite3") as snapshot_db:
                db.backup(snapshot_db)
        # Only durable published files, never transient worker files or credentials.
        for name in ("artifacts", "trade-archives"):
            if not (source / name).exists():
                continue
            for path in (source / name).rglob("*"):
                if path.is_symlink():
                    raise ValueError("Data snapshot cannot contain symbolic links")
                if not path.is_file() or path.suffix not in (
                    ".json",
                    ".zip",
                    ".sha256",
                ):
                    continue
                target = staging / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        files: dict[str, str] = {}
        manifest = {"version": 1, "files": files}
        for path in staging.rglob("*"):
            if path.is_file():
                digest = file_hash(path)
                if path.suffix in (".json", ".zip") and path.stem != digest:
                    raise ValueError("Source artifact integrity check failed")
                files[str(path.relative_to(staging))] = digest
        (staging / "backup-manifest.json").write_text(
            json.dumps(manifest, sort_keys=True)
        )
        verify(staging)
        publish(staging, destination)


def restore(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError("Restore requires a new destination")
    verify(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=destination.parent, prefix=".lab-restore-"
    ) as directory:
        staging = Path(directory) / "restored"
        shutil.copytree(source, staging, symlinks=False)
        verify(staging)
        publish(staging, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore", "verify"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, nargs="?")
    args = parser.parse_args()
    if args.operation == "verify":
        verify(args.source)
    else:
        if args.destination is None:
            parser.error("destination is required")
        (backup if args.operation == "backup" else restore)(
            args.source, args.destination
        )


if __name__ == "__main__":
    main()
