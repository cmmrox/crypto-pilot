"""Owner-console Binance reads share connections, never credentials, and fail fast."""

from __future__ import annotations

import pytest
from app.execution import binance_client as bc


@pytest.fixture(autouse=True)
def _empty_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bc, "_console_pools", {})


@pytest.mark.asyncio
async def test_console_reads_share_one_pool_per_environment() -> None:
    public = bc.console_client("DEMO")
    signed = bc.console_client("DEMO", api_key="k", api_secret="s")
    live = bc.console_client("LIVE")

    assert public._client is signed._client
    assert live._client is not public._client
    assert (public._api_key, signed._api_key) == (None, "k")
    await bc.close_console_clients()


@pytest.mark.asyncio
async def test_console_reads_fail_fast() -> None:
    client = bc.console_client("DEMO")

    assert client._max_retries == 1
    assert client._client.timeout.read == bc.CONSOLE_TIMEOUT_SECONDS
    await bc.close_console_clients()


@pytest.mark.asyncio
async def test_leaving_a_console_client_keeps_the_pool_open() -> None:
    async with bc.console_client("DEMO") as client:
        pool = client._client

    assert not pool.is_closed
    await bc.close_console_clients()
    assert pool.is_closed
    assert bc.console_client("DEMO")._client is not pool
    await bc.close_console_clients()


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown environment"):
        bc.console_client("PAPER")
