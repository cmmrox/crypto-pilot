"""SMS gateway abstraction over notify.lk (INTEGRATIONS.md §2).

Dependency inversion: the notifier depends on the SmsGateway protocol, tested with
FakeSmsGateway and delivered live via NotifyLkGateway. Fire-and-log — a delivery
failure never blocks trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.logging import get_logger

_log = get_logger("sms")

NOTIFY_LK_URL = "https://app.notify.lk/api/v1/send"


@dataclass(frozen=True)
class SmsResult:
    ok: bool
    detail: str


class SmsGateway(Protocol):
    async def send(self, to: str, message: str) -> SmsResult: ...


class NotifyLkGateway:
    """Live notify.lk HTTP gateway."""

    def __init__(
        self,
        user_id: str,
        api_key: str,
        sender_id: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user_id = user_id
        self._api_key = api_key
        self._sender_id = sender_id
        self._client = client or httpx.AsyncClient(timeout=15.0)
        self._owns = client is None

    async def send(self, to: str, message: str) -> SmsResult:
        """Send one SMS. notify.lk expects the number as 9471XXXXXXX (no +)."""
        params = {
            "user_id": self._user_id,
            "api_key": self._api_key,
            "sender_id": self._sender_id,
            "to": to.lstrip("+").replace(" ", ""),
            "message": message[:320],
        }
        try:
            resp = await self._client.post(NOTIFY_LK_URL, data=params)
            body: object = {"raw": resp.text}
            if resp.headers.get("content-type", "").startswith("application/json"):
                body = resp.json()
            status_ok = (
                isinstance(body, dict)
                and str(body.get("status", "")).lower() == "success"
            )
            if resp.status_code == 200 and status_ok:
                return SmsResult(True, "delivered")
            # Provider bodies may reflect submitted form fields (including the
            # API key, phone and OTP message). Never propagate them to callers,
            # logs or the web UI.
            return SmsResult(False, "provider rejected request")
        except (httpx.TransportError, httpx.TimeoutException):
            return SmsResult(False, "provider transport error")
        except Exception:
            # send() must never raise: a delivery/parse failure (e.g. malformed
            # JSON, a non-object body) must degrade to a failed SmsResult, not
            # propagate up through notify() and roll back a trade whose exchange
            # order already filled. The exception detail may echo provider form
            # fields (api_key, OTP), so it is never logged or returned.
            _log.warning("sms_send_unexpected_error", url=NOTIFY_LK_URL)
            return SmsResult(False, "provider response error")
        finally:
            if self._owns:
                await self._client.aclose()
                self._client = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        if self._owns:
            await self._client.aclose()
