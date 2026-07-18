"""FastAPI dependencies: authenticated user resolution with session revocation."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, decode_token
from app.db.models import User
from app.db.session import get_session
from app.services.auth import get_active_session

_bearer = HTTPBearer(auto_error=False)


class CurrentUser:
    """The authenticated owner plus the session id backing the request."""

    def __init__(self, user: User, sid: str) -> None:
        self.user = user
        self.sid = sid


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """Resolve the current user from a valid access token with a live session."""
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(creds.credentials, expected_purpose="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sid = claims.get("sid")
    if not sid or await get_active_session(session, sid) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session revoked or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = (
        await session.execute(select(User).where(User.id == int(claims["sub"])))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown user")
    return CurrentUser(user=user, sid=sid)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
