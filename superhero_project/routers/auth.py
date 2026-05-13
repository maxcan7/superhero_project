"""GitHub OAuth router: login redirect, token exchange, and logout."""

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter
from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.config import settings
from superhero_project.db.models import User
from superhero_project.dependencies import DB

router = APIRouter(prefix="/auth", tags=["auth"])

_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL = "https://api.github.com/user"


async def _fetch_github_user(code: str) -> tuple[int, str, str]:
    """Exchange the OAuth callback code for a GitHub token, then fetch the user profile.

    Returns (github_id, login, display_name).
    """

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": f"{settings.base_url}/auth/callback",
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access_token: str = token_resp.json()["access_token"]

        user_resp = await client.get(
            _GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        user_resp.raise_for_status()
        gh = user_resp.json()

    return int(gh["id"]), str(gh["login"]), str(gh.get("name") or gh["login"])


async def _upsert_user(
    gh_id: int, gh_username: str, display_name: str, db: AsyncSession
) -> User:
    """Insert or update the users row for the given GitHub identity."""
    result = await db.execute(select(User).where(User.github_id == gh_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            github_id=gh_id, github_username=gh_username, display_name=display_name
        )
        db.add(user)
    else:
        user.github_username = gh_username
        user.display_name = display_name
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/login")
async def login() -> RedirectResponse:
    """Redirect the user to GitHub's OAuth authorization page."""
    params = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": f"{settings.base_url}/auth/callback",
            "scope": "read:user",
        }
    )
    return RedirectResponse(f"{_GITHUB_AUTH_URL}?{params}")


@router.get("/callback")
async def callback(request: Request, code: str, db: DB) -> RedirectResponse:
    """Handle the GitHub OAuth callback, upsert the user, and set the session."""
    gh_id, gh_username, display_name = await _fetch_github_user(code)
    user = await _upsert_user(gh_id, gh_username, display_name, db)
    request.session["user_id"] = user.id
    request.session["role"] = user.role.value
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to the home page."""
    request.session.clear()
    return RedirectResponse("/")
