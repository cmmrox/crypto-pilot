"""Codex device-code authentication (owner-driven, re-authenticatable).

Flow: start_login() returns a verification URL + user code; the owner opens the URL
and enters the code; a background task waits for completion and the SDK persists the
session under CODEX_HOME (a mounted volume). status()/is_authenticated() let the UI
reflect state and offer re-authentication or logout.

The news module is isolated: it never imports trading code and holds no exchange keys.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from openai_codex import AsyncCodex

_log = get_logger("codex_auth")


def _ensure_codex_home() -> str:
    home = get_settings().codex_home
    os.makedirs(home, exist_ok=True)
    os.environ["CODEX_HOME"] = home
    return home


@dataclass
class LoginState:
    login_id: str
    verification_url: str
    user_code: str
    status: str = "pending"  # pending | completed | failed | cancelled
    detail: str = ""
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class CodexAuthService:
    """Owns in-flight device-code logins and the authenticated-status check."""

    def __init__(self) -> None:
        self._logins: dict[str, LoginState] = {}

    def _client(self) -> AsyncCodex:
        _ensure_codex_home()
        from openai_codex import AsyncCodex

        return AsyncCodex()

    async def start_login(self) -> LoginState:
        """Begin a device-code login; returns the URL + code for the owner."""
        client = self._client()
        handle = await client.login_chatgpt_device_code()
        state = LoginState(
            login_id=handle.login_id,
            verification_url=handle.verification_url,
            user_code=handle.user_code,
        )
        self._logins[state.login_id] = state

        async def _wait() -> None:
            try:
                await handle.wait()
                state.status = "completed"
                state.detail = "authenticated"
                _log.info("codex_login_completed", login_id=state.login_id)
            except Exception as exc:
                state.status = "failed"
                state.detail = str(exc)
                _log.warning("codex_login_failed", error=str(exc))
            finally:
                await client.close()

        state.task = asyncio.create_task(_wait(), name=f"codex-login-{state.login_id}")
        return state

    def login_status(self, login_id: str) -> LoginState | None:
        return self._logins.get(login_id)

    async def is_authenticated(self) -> bool:
        """True if a Codex session is active (account() succeeds)."""
        client = self._client()
        try:
            await client.account()
            return True
        except Exception:
            return False
        finally:
            await client.close()

    async def logout(self) -> None:
        client = self._client()
        try:
            await client.logout()
        except Exception as exc:
            _log.warning("codex_logout_error", error=str(exc))
        finally:
            await client.close()


codex_auth = CodexAuthService()
