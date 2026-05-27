"""Tests for contributor profiles, tag browsing, and personal pages."""

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
    assert published_article.page_name in (await client.get("/tags/hero")).text


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
        published_article.page_name
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


# ── My articles (/me/articles) ─────────────────────────────────────────────────


async def test_my_articles_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    assert (await client.get("/me/articles")).status_code == 401


async def test_my_articles_empty_state(auth_client: AsyncClient) -> None:
    """Authenticated user with no articles sees the empty state."""
    assert "written any articles yet." in (await auth_client.get("/me/articles")).text


async def test_my_articles_shows_all_statuses(
    auth_client: AsyncClient,
    draft_article: Article,
    published_article: Article,
    pending_article: Article,
) -> None:
    """All of the user's articles appear regardless of status."""
    text = (await auth_client.get("/me/articles")).text
    assert draft_article.page_name in text
    assert published_article.page_name in text
    assert pending_article.page_name in text
    assert "Changes requested" not in text


async def test_my_articles_excludes_other_users(
    other_auth_client: AsyncClient, draft_article: Article
) -> None:
    """Articles authored by other users do not appear on this page."""
    text = (await other_auth_client.get("/me/articles")).text
    assert draft_article.page_name not in text


async def test_my_articles_moderator_note_callout(
    auth_client: AsyncClient,
    db: AsyncSession,
    draft_article: Article,
) -> None:
    """My-articles page shows revision callout for drafts with a moderator_note."""
    draft_article.moderator_note = "needs more detail"
    await db.commit()
    assert (
        "Changes requested: needs more detail"
        in (await auth_client.get("/me/articles")).text
    )
