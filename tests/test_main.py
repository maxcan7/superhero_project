"""Tests for per-endpoint rate limiting."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_auth_login_rate_limit(client: AsyncClient) -> None:
    """Exceeding the auth rate limit returns 429."""
    for _ in range(20):
        await client.get("/auth/login", follow_redirects=False)
    resp = await client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 429
