"""Restore drills use isolated directories and include committed WAL transactions."""

import sqlite3

import pytest

from experiment_lab.adapters.artifacts import Artifacts
from experiment_lab.adapters.store import Store
from experiment_lab.backup import backup, restore


def test_backup_restores_wal_and_artifacts_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source"
    artifacts = Artifacts(source / "artifacts")
    digest = artifacts.put({"retained": "0.00000001"})
    store = Store(source / "lab.sqlite3")
    # Keep a connection open so the committed row can remain in WAL.
    with store.connection() as connection:
        connection.execute("PRAGMA wal_autocheckpoint=0")
        study = store.create_study({"dataset_id": digest})
        backup(source, tmp_path / "snapshot")
    restore(tmp_path / "snapshot", tmp_path / "restored")
    restored = Store(tmp_path / "restored/lab.sqlite3")
    assert restored.study(study["id"])["config"]["dataset_id"] == digest
    assert Artifacts(tmp_path / "restored/artifacts").get(digest) == {
        "retained": "0.00000001"
    }
    with pytest.raises(FileExistsError):
        restore(tmp_path / "snapshot", source)
    with sqlite3.connect(tmp_path / "restored/lab.sqlite3") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_restore_detects_corruption_before_publishing(tmp_path):
    source = tmp_path / "source"
    digest = Artifacts(source / "artifacts").put({"value": "1"})
    Store(source / "lab.sqlite3")
    backup(source, tmp_path / "snapshot")
    (tmp_path / "snapshot/artifacts" / f"{digest}.json").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        restore(tmp_path / "snapshot", tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_disk_full_does_not_publish_partial_backup(tmp_path, monkeypatch):
    import errno

    source = tmp_path / "source"
    Artifacts(source / "artifacts").put({"value": "1"})
    Store(source / "lab.sqlite3")

    def full(*args, **kwargs):
        raise OSError(errno.ENOSPC, "Disk full")

    monkeypatch.setattr("experiment_lab.backup.shutil.copyfile", full)
    with pytest.raises(OSError):
        backup(source, tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()
    assert not list(tmp_path.glob(".lab-backup-*"))
    assert Store(source / "lab.sqlite3").studies() == []


def test_archive_files_are_preserved_without_loading_whole_partition(tmp_path):
    import hashlib

    source = tmp_path / "source"
    Store(source / "lab.sqlite3")
    archive = source / "trade-archives"
    archive.mkdir()
    content = b"partition-bytes"
    digest = hashlib.sha256(content).hexdigest()
    (archive / f"{digest}.zip").write_bytes(content)
    (archive / "trades-2024-01.sha256").write_text(digest)
    backup(source, tmp_path / "snapshot")
    restore(tmp_path / "snapshot", tmp_path / "restored")
    assert (
        tmp_path / "restored/trade-archives" / f"{digest}.zip"
    ).read_bytes() == content


def test_restore_rejects_unlisted_files(tmp_path):
    source = tmp_path / "source"
    Store(source / "lab.sqlite3")
    backup(source, tmp_path / "snapshot")
    (tmp_path / "snapshot/extra.txt").write_text("unexpected")
    with pytest.raises(ValueError, match="manifest"):
        restore(tmp_path / "snapshot", tmp_path / "restored")


def test_backup_rejects_missing_referenced_dataset(tmp_path):
    source = tmp_path / "source"
    Store(source / "lab.sqlite3").create_study({"dataset_id": "a" * 64})
    with pytest.raises(ValueError, match="referenced artifact"):
        backup(source, tmp_path / "snapshot")
    assert not (tmp_path / "snapshot").exists()
