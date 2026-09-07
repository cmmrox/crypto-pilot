"""Owner-authenticated, allowlisted BFF. Private worker endpoints are never proxied."""

import json
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUserDep
from app.core.config import get_settings
from app.experiment_lab.client import LabClient

router = APIRouter(prefix="/api/experiment-lab", tags=["experiment-lab"])
_READ = re.compile(
    r"(?:strategies|studies|studies/[a-f0-9]{32}(?:/skill)?|iterations/[a-f0-9]{32}/(?:artifact|candidate))"
)
_WRITE = re.compile(
    r"(?:studies|studies/[a-f0-9]{32}/iterations|iterations/[a-f0-9]{32}/(?:cancel|retry-review))"
)


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def gateway(path: str, request: Request, _current: CurrentUserDep) -> Any:
    if _current.user.role != "owner":
        raise HTTPException(403, "Owner access required")
    allowed = _READ if request.method == "GET" else _WRITE
    if allowed.fullmatch(path) is None:
        raise HTTPException(404, "Lab route not found")
    settings = get_settings()
    if not settings.lab_url or len(settings.lab_service_token) < 32:
        raise HTTPException(503, "Experiment Lab is not configured")
    client = LabClient(settings.lab_url, settings.lab_service_token)
    body = None
    if request.method == "POST":
        raw = await request.body()
        if len(raw) > 64 * 1024:
            raise HTTPException(413, "Lab request exceeds 64 KiB")
        try:
            body = json.loads(raw) if raw else None
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Request must contain valid JSON") from None
    if body is not None and not isinstance(body, dict):
        raise HTTPException(422, "Request must be a JSON object")
    try:
        result = await client.request_response(
            request.method,
            "/" + path,
            body=body,
            key=request.headers.get("Idempotency-Key"),
            params=list(request.query_params.multi_items()),
        )
        return (
            Response(status_code=204)
            if result.status_code == 204
            else JSONResponse(content=result.json(), status_code=result.status_code)
        )
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status in (404, 409, 422):
            try:
                detail = error.response.json().get("detail", "Lab request rejected")
            except (ValueError, AttributeError):
                detail = "Lab request rejected"
            raise HTTPException(status, detail) from None
        raise HTTPException(503, "Experiment Lab is unavailable") from None
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Experiment Lab is unavailable") from None
