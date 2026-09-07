"""Streaming, checksum-pinned Binance trades. No synthetic intrabar paths."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import tempfile
import zipfile
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import httpx
import pandas as pd

from experiment_lab.adapters.binance import ARCHIVE, BinanceData


class TradeArchive:
    def __init__(self, root: Path, data_kind: str = "trades"):
        if data_kind not in ("trades", "aggTrades"):
            raise ValueError("Unsupported Binance trade archive kind")
        self.data_kind = data_kind
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.provenance: list[dict[str, str]] = []

    def partition(self, month: str) -> Path:
        if re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", month) is None:
            raise ValueError("Invalid archive partition date")
        daily = len(month) == 10
        pd.Timestamp(month if daily else f"{month}-01", tz="UTC")
        # Once downloaded, a local partition is immutable. Reproduction verifies
        # its original checksum rather than silently accepting upstream revisions.
        index = self.root / f"{self.data_kind}-{month}.sha256"
        if index.exists():
            digest = index.read_text().strip()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid archive checksum index")
            target = self.root / f"{digest}.zip"
        else:
            frequency = "daily" if daily else "monthly"
            url = f"{ARCHIVE}/{frequency}/{self.data_kind}/BTCUSDT/BTCUSDT-{self.data_kind}-{month}.zip"
            with httpx.Client(timeout=120, follow_redirects=False) as client:
                digest = BinanceData.get(client, url + ".CHECKSUM").text.split()[0]
                if len(digest) != 64 or any(
                    c not in "0123456789abcdef" for c in digest
                ):
                    raise ValueError("Invalid Binance archive checksum")
                target = self.root / f"{digest}.zip"
                with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as output:
                    temporary = Path(output.name)
                    try:
                        with client.stream("GET", url) as response:
                            response.raise_for_status()
                            size = 0
                            for block in response.iter_bytes(1024 * 1024):
                                size += len(block)
                                if size > 4_000_000_000:
                                    raise ValueError(
                                        "Archive exceeds the 4 GB partition budget"
                                    )
                                output.write(block)
                        output.flush()
                        os.fsync(output.fileno())
                    except BaseException:
                        temporary.unlink(missing_ok=True)
                        raise
                if file_hash(temporary) != digest:
                    temporary.unlink(missing_ok=True)
                    raise ValueError("Binance archive checksum mismatch")
                os.replace(temporary, target)
                # Index publication is atomic too; an orphan zip is harmless.
                with tempfile.NamedTemporaryFile(
                    dir=self.root, mode="w", delete=False
                ) as pointer:
                    pointer.write(digest)
                    pointer.flush()
                    os.fsync(pointer.fileno())
                    pointer_path = Path(pointer.name)
                os.replace(pointer_path, index)
        if file_hash(target) != digest:
            raise ValueError("Cached trade archive integrity failed")
        self.provenance.append(
            {
                "partition": month,
                "sha256": digest,
                "source": "BINANCE_USDM_" + self.data_kind.upper(),
            }
        )
        return target

    def trades(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> Iterator[tuple[pd.Timestamp, Decimal]]:
        daily = end - start <= pd.Timedelta(days=3)
        cursor = start.normalize() if daily else start.normalize().replace(day=1)
        previous_id = None
        previous_time = None
        while cursor < end:
            path = self.partition(cursor.strftime("%Y-%m-%d" if daily else "%Y-%m"))
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                if len(members) != 1 or members[0].file_size > 20_000_000_000:
                    raise ValueError("Unexpected trade archive layout or expansion")
                with archive.open(members[0]) as raw:
                    reader = csv.DictReader(io.TextIOWrapper(raw))
                    id_field = "id" if self.data_kind == "trades" else "agg_trade_id"
                    time_field = (
                        "time" if self.data_kind == "trades" else "transact_time"
                    )
                    if not {id_field, "price", time_field} <= set(
                        reader.fieldnames or []
                    ):
                        raise ValueError("Unsupported Binance trade columns")
                    for row in reader:
                        identity = int(row[id_field])
                        timestamp_ms = int(row[time_field])
                        if previous_id is not None and identity != previous_id + 1:
                            raise ValueError("Trade ID gap or duplication")
                        if previous_time is not None and timestamp_ms < previous_time:
                            raise ValueError("Nonchronological aggregate trades")
                        previous_id, previous_time = identity, timestamp_ms
                        timestamp = pd.Timestamp(timestamp_ms, unit="ms", tz="UTC")
                        if start <= timestamp < end:
                            price = Decimal(row["price"])
                            if not price.is_finite() or price <= 0:
                                raise ValueError("Invalid trade price")
                            yield timestamp, price
            cursor += pd.Timedelta(days=1) if daily else pd.offsets.MonthBegin(1)


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()
