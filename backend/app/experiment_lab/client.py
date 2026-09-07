"""Small authenticated client for the private experiment service."""

from typing import Any

import httpx


class LabClient:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    async def request_response(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        key: str | None = None,
        params: list[tuple[str, str]] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"}
        if key:
            headers["Idempotency-Key"] = key
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.request(
                method,
                self.url + path,
                headers=headers,
                json=body,
                params=tuple(params) if params else None,
            )
        response.raise_for_status()
        return response

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        key: str | None = None,
    ) -> Any:
        response = await self.request_response(method, path, body=body, key=key)
        return None if response.status_code == 204 else response.json()
