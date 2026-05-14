"""Tests for the GitHub OAuth auth router."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.routers.auth import _fetch_github_user

pytestmark = pytest.mark.anyio


# ── Redirects ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("use_auth", "path", "expected_in_location"),
    [
        pytest.param(
            False, "/auth/login", "github.com/login/oauth/authorize", id="login"
        ),
        pytest.param(True, "/auth/logout", "/", id="logout"),
    ],
)
async def test_auth_redirect(
    client: AsyncClient,
    auth_client: AsyncClient,
    use_auth: bool,
    path: str,
    expected_in_location: str,
) -> None:
    """Login and logout redirect to the expected location."""
    c = auth_client if use_auth else client
    resp = await c.get(path, follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert expected_in_location in resp.headers["location"]


# ── OAuth callback ─────────────────────────────────────────────────────────────


async def test_callback_new_user(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """OAuth callback with a new GitHub id creates a user record."""
    monkeypatch.setattr(
        "superhero_project.routers.auth._fetch_github_user",
        AsyncMock(return_value=(42, "newuser", "New User")),
    )
    await client.get("/auth/callback?code=x", follow_redirects=False)
    result = await db.execute(select(User).where(User.github_id == 42))
    assert result.scalar_one_or_none() is not None


async def test_fetch_github_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """_fetch_github_user exchanges a code for a token and returns the GitHub
    identity."""
    mock_token = MagicMock()
    mock_token.json.return_value = {"access_token": "tok"}
    mock_token.raise_for_status = MagicMock()

    mock_user = MagicMock()
    mock_user.json.return_value = {"id": 7, "login": "ghuser", "name": "GH User"}
    mock_user.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_token)
    mock_client.get = AsyncMock(return_value=mock_user)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(
        "superhero_project.routers.auth.httpx.AsyncClient", lambda: mock_client
    )

    assert await _fetch_github_user("code") == (7, "ghuser", "GH User")


async def test_callback_existing_user_updated(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """OAuth callback with a known GitHub id updates login and display name."""
    existing = User(
        github_id=42,
        github_username="oldlogin",
        display_name="Old Name",
        role=UserRole.contributor,
    )
    db.add(existing)
    await db.commit()

    monkeypatch.setattr(
        "superhero_project.routers.auth._fetch_github_user",
        AsyncMock(return_value=(42, "newlogin", "New Name")),
    )
    await client.get("/auth/callback?code=x", follow_redirects=False)
    await db.refresh(existing)
    assert existing.github_username == "newlogin"
