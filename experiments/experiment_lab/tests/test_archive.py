"""Synthetic archive fixtures exercise ingestion guards, not trading performance."""

import hashlib
import zipfile
from decimal import Decimal

import pandas as pd
import pytest

from experiment_lab.adapters.trade_archive import TradeArchive
from experiment_lab.domain.failures import failure_code


def cached_archive(tmp_path, body):
    archive = TradeArchive(tmp_path)
    temporary = tmp_path / "fixture.zip"
    with zipfile.ZipFile(temporary, "w") as target:
        target.writestr("BTCUSDT-trades-2024-01-01.csv", body)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    temporary.rename(tmp_path / f"{digest}.zip")
    (tmp_path / "trades-2024-01-01.sha256").write_text(digest)
    return archive


def test_raw_trade_archive_preserves_actual_order_and_decimal_price(tmp_path):
    archive = cached_archive(
        tmp_path,
        "id,price,qty,quote_qty,time,is_buyer_maker\n1,40000.01,1,40000.01,1704067200000,false\n2,40000.02,1,40000.02,1704067200001,true\n",
    )
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    rows = list(archive.trades(start, start + pd.Timedelta(hours=4)))
    assert [price for _, price in rows] == [Decimal("40000.01"), Decimal("40000.02")]
    assert archive.provenance[0]["source"] == "BINANCE_USDM_TRADES"


def test_raw_archive_gap_fails_closed_with_public_reason(tmp_path):
    archive = cached_archive(
        tmp_path, "id,price,time\n1,40000,1704067200000\n3,40001,1704067200001\n"
    )
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    with pytest.raises(ValueError) as error:
        list(archive.trades(start, start + pd.Timedelta(hours=4)))
    assert failure_code(error.value) == "TRADE_ID_GAP"


def test_corrupted_cached_archive_is_not_used(tmp_path):
    archive = cached_archive(tmp_path, "id,price,time\n1,40000,1704067200000\n")
    archive.partition("2024-01-01").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        archive.partition("2024-01-01")


def test_arbitrary_exception_does_not_leak_secret_in_failure_code():
    assert (
        failure_code(RuntimeError("secret from an external response"))
        == "WORKER_FAILED"
    )
