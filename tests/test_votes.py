"""Tests for the votes router: cast, update, and remove votes on articles."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import User
from superhero_project.db.models import Vote

pytestmark = pytest.mark.anyio


# ── Auth ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        pytest.param("put", {"value": 1}, id="cast"),
        pytest.param("delete", None, id="remove"),
    ],
)
async def test_vote_requires_auth(
    client: AsyncClient, published_article: Article, method: str, payload: dict | None
) -> None:
    """PUT and DELETE return 401 without a session."""
    kwargs = {"json": payload} if payload is not None else {}
    assert (
        await getattr(client, method)(f"/votes/{published_article.page_name}", **kwargs)
    ).status_code == 401


# ── Not found ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        pytest.param("get", None, id="get"),
        pytest.param("put", {"value": 1}, id="cast"),
        pytest.param("delete", None, id="remove"),
    ],
)
async def test_vote_article_not_found(
    auth_client: AsyncClient, method: str, payload: dict | None
) -> None:
    """All vote endpoints return 404 for a nonexistent article."""
    kwargs = {"json": payload} if payload is not None else {}
    assert (
        await getattr(auth_client, method)("/votes/nonexistent", **kwargs)
    ).status_code == 404


# ── GET ───────────────────────────────────────────────────────────────────────


async def test_get_votes_empty(client: AsyncClient, published_article: Article) -> None:
    """Returns zero counts when no votes have been cast."""
    assert (await client.get(f"/votes/{published_article.page_name}")).json() == {
        "article_id": published_article.id,
        "upvotes": 0,
        "downvotes": 0,
        "score": 0,
    }


async def test_get_votes_counts(
    client: AsyncClient,
    db: AsyncSession,
    published_article: Article,
    user: User,
    other_user: User,
) -> None:
    """Correctly tallies upvotes and downvotes from multiple users."""
    db.add(Vote(article_id=published_article.id, user_id=user.id, value=1))
    db.add(Vote(article_id=published_article.id, user_id=other_user.id, value=-1))
    await db.commit()
    assert (await client.get(f"/votes/{published_article.page_name}")).json() == {
        "article_id": published_article.id,
        "upvotes": 1,
        "downvotes": 1,
        "score": 0,
    }


# ── PUT ───────────────────────────────────────────────────────────────────────


async def test_cast_vote_invalid_value(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """Values other than +1 or -1 return 422."""
    url = f"/votes/{published_article.page_name}"
    assert (await auth_client.put(url, json={"value": 2})).status_code == 422


@pytest.mark.parametrize(
    ("value", "counter"),
    [
        pytest.param(1, "upvotes", id="upvote"),
        pytest.param(-1, "downvotes", id="downvote"),
    ],
)
async def test_cast_vote(
    auth_client: AsyncClient, published_article: Article, value: int, counter: str
) -> None:
    """Casting +1 increments upvotes; -1 increments downvotes."""
    url = f"/votes/{published_article.page_name}"
    data = (await auth_client.put(url, json={"value": value})).json()
    assert data[counter] == 1


async def test_update_vote_replaces_existing(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """A second PUT updates the existing vote instead of inserting a duplicate."""
    url = f"/votes/{published_article.page_name}"
    await auth_client.put(url, json={"value": 1})
    data = (await auth_client.put(url, json={"value": -1})).json()
    assert data["upvotes"] == 0


# ── DELETE ────────────────────────────────────────────────────────────────────


async def test_remove_vote(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """Removing an existing vote returns 204."""
    await auth_client.put(f"/votes/{published_article.page_name}", json={"value": 1})
    assert (
        await auth_client.delete(f"/votes/{published_article.page_name}")
    ).status_code == 204


async def test_remove_vote_not_cast(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """Returns 404 when the user has no vote to remove."""
    assert (
        await auth_client.delete(f"/votes/{published_article.page_name}")
    ).status_code == 404
