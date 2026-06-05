"""Tests for SecurityHeadersMiddleware."""

import asyncio

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from superhero_project.middleware import SecurityHeadersMiddleware

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        pytest.param("x-content-type-options", "nosniff", id="x-content-type-options"),
        pytest.param("x-frame-options", "DENY", id="x-frame-options"),
        pytest.param(
            "referrer-policy", "strict-origin-when-cross-origin", id="referrer-policy"
        ),
        pytest.param(
            "content-security-policy",
            "default-src 'self'; script-src 'self'; style-src 'self'",
            id="content-security-policy",
        ),
    ],
)
async def test_security_header_present(header: str, expected: str) -> None:
    """SecurityHeadersMiddleware injects the expected value for each security header."""

    async def plain_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async with AsyncClient(
        transport=ASGITransport(SecurityHeadersMiddleware(plain_app)),
        base_url="http://test",
    ) as client:
        resp = await client.get("/")

    assert resp.headers[header] == expected


@pytest.mark.parametrize(
    "scope_type",
    [
        pytest.param("lifespan", id="lifespan"),
        pytest.param("websocket", id="websocket"),
    ],
)
async def test_non_http_scope_passes_through(scope_type: str) -> None:
    """SecurityHeadersMiddleware passes non-HTTP scopes directly to the inner app."""
    called_with: list[str] = []

    async def inner(scope, receive, send):
        called_with.append(scope["type"])
        await asyncio.sleep(0)

    await SecurityHeadersMiddleware(inner)({"type": scope_type}, None, None)
    assert called_with == [scope_type]
