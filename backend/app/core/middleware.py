"""Security headers + request-size limiting (SECURITY_GUIDELINES.md §Hardening)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MAX_BODY_BYTES = 1_000_000  # 1 MB — API payloads are small

# A strict CSP: the SPA is same-origin; no inline/eval, no third-party origins.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response."""

    def __init__(self, app: object, *, hsts: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if self._hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class BodySizeLimitMiddleware:
    """Reject oversized fixed-length and streamed request bodies.

    This is pure ASGI middleware so chunked/lengthless bodies are bounded while
    they are received, before Starlette or Pydantic can buffer and parse them.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > MAX_BODY_BYTES:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        messages: list[dict[str, Any]] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            total += len(message.get("body", b""))
            if total > MAX_BODY_BYTES:
                await self._reject(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> dict[str, Any]:
            if messages:
                return messages.pop(0)
            # Streaming responses may continue listening for a client
            # disconnect after the request body has been replayed.
            return cast(dict[str, Any], await receive())

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope: Any, receive: Any, send: Any) -> None:
        response = JSONResponse({"detail": "request body too large"}, status_code=413)
        await response(scope, receive, send)
