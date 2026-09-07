"""The UI cannot access internal worker commands through the authenticated BFF."""

from tests.conftest import auth_headers


async def test_lab_is_authenticated_and_disabled_by_default(app_client, owner):
    assert (await app_client.get("/api/experiment-lab/studies")).status_code == 401
    headers = await auth_headers(app_client)
    assert (await app_client.get("/api/experiment-lab/studies", headers=headers)).status_code == 503
    assert (
        await app_client.post(
            "/api/experiment-lab/jobs/claim", headers=headers, json={"kind": "REPLAY"}
        )
    ).status_code == 404


async def test_lab_gateway_forwards_pagination_and_handles_invalid_upstream(
    app_client, owner, monkeypatch
):
    import httpx
    import respx
    from app.core.config import get_settings

    headers = await auth_headers(app_client)
    settings = get_settings()
    monkeypatch.setattr(settings, "lab_url", "http://lab.test")
    monkeypatch.setattr(settings, "lab_service_token", "x" * 32)
    identity = "a" * 32
    with respx.mock:
        route = respx.get(
            f"http://lab.test/studies/{identity}", params={"before": "20", "limit": "10"}
        ).mock(return_value=httpx.Response(200, json={"iterations": [], "next_cursor": None}))
        response = await app_client.get(
            f"/api/experiment-lab/studies/{identity}?before=20&limit=10", headers=headers
        )
        assert response.status_code == 200
        assert route.called
        respx.get("http://lab.test/studies").mock(
            return_value=httpx.Response(200, text="<html>unavailable</html>")
        )
        response = await app_client.get("/api/experiment-lab/studies", headers=headers)
        assert response.status_code == 503


async def test_lab_gateway_preserves_created_and_accepted_status(app_client, owner, monkeypatch):
    import httpx
    import respx
    from app.core.config import get_settings

    headers = await auth_headers(app_client)
    settings = get_settings()
    monkeypatch.setattr(settings, "lab_url", "http://lab.test")
    monkeypatch.setattr(settings, "lab_service_token", "x" * 32)
    with respx.mock:
        respx.post("http://lab.test/studies").mock(
            return_value=httpx.Response(201, json={"id": "a" * 32})
        )
        response = await app_client.post("/api/experiment-lab/studies", headers=headers, json={})
        assert response.status_code == 201


async def test_gateway_rejects_bad_body_and_preserves_safe_errors(app_client, owner, monkeypatch):
    import httpx
    import respx
    from app.core.config import get_settings

    headers = await auth_headers(app_client)
    settings = get_settings()
    monkeypatch.setattr(settings, "lab_url", "http://lab.test")
    monkeypatch.setattr(settings, "lab_service_token", "x" * 32)
    for payload, status in [(b"[1]", 422), (b"broken", 422), (b"x" * 65537, 413)]:
        response = await app_client.post(
            "/api/experiment-lab/studies", headers=headers, content=payload
        )
        assert response.status_code == status
    with respx.mock:
        route = respx.get("http://lab.test/studies")
        for upstream, body, expected in [
            (409, "unavailable", 409),
            (422, '["unexpected"]', 422),
            (404, '{"detail":"Study not found"}', 404),
            (500, '{"detail":"private internals"}', 503),
        ]:
            route.mock(return_value=httpx.Response(upstream, text=body))
            response = await app_client.get("/api/experiment-lab/studies", headers=headers)
            assert response.status_code == expected
            assert "private internals" not in response.text
        route.mock(side_effect=httpx.ConnectError("private service address"))
        response = await app_client.get("/api/experiment-lab/studies", headers=headers)
        assert response.status_code == 503
        assert "private service address" not in response.text
