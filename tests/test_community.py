"""Tests for contributor profiles and tag browsing (M5 commit 2)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import User

pytestmark = pytest.mark.anyio


# ── Empty states ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param("/tags", "No tags yet.", id="tag-index"),
        pytest.param(
            "/tags/unknown-tag", "No published articles with this tag.", id="tag-detail"
        ),
    ],
)
async def test_empty_state(client: AsyncClient, url: str, expected: str) -> None:
    """Empty-state message shown when no matching published articles exist."""
    assert expected in (await client.get(url)).text


# ── Tag index (/tags) ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param("hero", id="tag-name"),
        pytest.param("1", id="count"),
    ],
)
async def test_tag_index_content(
    client: AsyncClient, published_article: Article, expected: str
) -> None:
    """Tag index lists each tag name and its article count."""
    assert expected in (await client.get("/tags")).text


# ── Tag detail (/tags/{tag}) ───────────────────────────────────────────────────


async def test_tag_detail_shows_article(
    client: AsyncClient, published_article: Article
) -> None:
    """Tag detail page lists published articles carrying the tag."""
    assert published_article.slug in (await client.get("/tags/hero")).text


async def test_tag_detail_excludes_unpublished(
    client: AsyncClient, db: AsyncSession, draft_article: Article
) -> None:
    """Draft articles do not appear on the tag detail page."""
    db.add(ArticleTag(article_id=draft_article.id, tag="draft-only"))
    await db.commit()
    assert (
        "No published articles with this tag."
        in (await client.get("/tags/draft-only")).text
    )


# ── Contributor profile (/contributors/{username}) ─────────────────────────────


async def test_contributor_not_found(client: AsyncClient) -> None:
    """Returns 404 for an unknown github username."""
    assert (await client.get("/contributors/nobody")).status_code == 404


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param("Test User", id="display-name"),
        pytest.param("@testuser", id="github-handle"),
    ],
)
async def test_contributor_profile_identity(
    client: AsyncClient, user: User, expected: str
) -> None:
    """Profile page renders the contributor's display name and GitHub handle."""
    assert expected in (await client.get(f"/contributors/{user.github_username}")).text


async def test_contributor_lists_published_articles(
    client: AsyncClient, user: User, published_article: Article
) -> None:
    """Published articles appear on the contributor's profile."""
    assert (
        published_article.slug
        in (await client.get(f"/contributors/{user.github_username}")).text
    )


async def test_contributor_excludes_unpublished(
    client: AsyncClient, user: User, draft_article: Article
) -> None:
    """Draft articles do not appear on the contributor's profile."""
    assert (
        "No published articles yet."
        in (await client.get(f"/contributors/{user.github_username}")).text
    )
