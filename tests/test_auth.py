"""Tests for the GitHub OAuth auth router."""

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import User
from superhero_project.db.models import UserRole

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
