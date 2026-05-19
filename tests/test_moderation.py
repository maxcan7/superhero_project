"""Tests for the moderation router: queue, submit, approve, reject, request-changes."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from tests.utils import ORG_META
from tests.utils import make_article

pytestmark = pytest.mark.anyio

_QUEUE_URLS = [
    pytest.param("/moderation/queue", id="json"),
    pytest.param("/moderation/queue/view", id="html"),
]

_MOD_ACTIONS = [
    pytest.param("approve", id="approve"),
    pytest.param("reject", id="reject"),
    pytest.param("request-changes", id="request-changes"),
]


# ── Queue access control ───────────────────────────────────────────────────────


@pytest.mark.parametrize("url", _QUEUE_URLS)
async def test_queue_requires_auth(client: AsyncClient, url: str) -> None:
    """Unauthenticated requests to both queue endpoints return 401."""
    assert (await client.get(url)).status_code == 401


@pytest.mark.parametrize("url", _QUEUE_URLS)
async def test_queue_contributor_forbidden(auth_client: AsyncClient, url: str) -> None:
    """Contributors cannot access either queue endpoint."""
    assert (await auth_client.get(url)).status_code == 403


async def test_queue_empty(mod_auth_client: AsyncClient) -> None:
    """Moderator sees empty list when no articles are pending."""
    assert (await mod_auth_client.get("/moderation/queue")).json() == []


async def test_queue_lists_pending(
    mod_auth_client: AsyncClient, pending_article: Article
) -> None:
    """Pending article appears in the queue."""
    [item] = (await mod_auth_client.get("/moderation/queue")).json()
    assert item["slug"] == pending_article.slug


async def test_queue_excludes_non_pending(
    mod_auth_client: AsyncClient,
    draft_article: Article,
    published_article: Article,
) -> None:
    """Draft and published articles do not appear in the queue."""
    assert (await mod_auth_client.get("/moderation/queue")).json() == []


# ── Queue HTML view ────────────────────────────────────────────────────────────


async def test_queue_view_renders_pending(
    mod_auth_client: AsyncClient, pending_article: Article
) -> None:
    """Moderator queue view renders the pending article's slug."""
    assert (
        pending_article.slug
        in (await mod_auth_client.get("/moderation/queue/view")).text
    )


async def test_queue_view_empty_state(mod_auth_client: AsyncClient) -> None:
    """Queue view shows empty-state message when no articles are pending."""
    assert (
        "No articles pending review"
        in (await mod_auth_client.get("/moderation/queue/view")).text
    )


# ── Submit ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def submit_scenario(
    request: pytest.FixtureRequest,
    client: AsyncClient,
    auth_client: AsyncClient,
    other_auth_client: AsyncClient,
    mod_auth_client: AsyncClient,
    draft_article: Article,
    pending_article: Article,
) -> tuple[AsyncClient, Article, int]:
    """Resolve a (client, article, expected_status) triple from indirect params."""
    client_name, article_name, expected = request.param
    ac = {
        "client": client,
        "auth_client": auth_client,
        "other_auth_client": other_auth_client,
        "mod_auth_client": mod_auth_client,
    }[client_name]
    article = {"draft_article": draft_article, "pending_article": pending_article}[
        article_name
    ]
    return ac, article, expected


@pytest.mark.parametrize(
    "submit_scenario",
    [
        pytest.param(("client", "draft_article", 401), id="unauthenticated"),
        pytest.param(("other_auth_client", "draft_article", 403), id="non-author"),
        pytest.param(("mod_auth_client", "draft_article", 403), id="moderator-blocked"),
        pytest.param(("auth_client", "pending_article", 409), id="non-draft"),
        pytest.param(("auth_client", "draft_article", 200), id="author"),
    ],
    indirect=True,
)
async def test_submit(submit_scenario: tuple[AsyncClient, Article, int]) -> None:
    """Submit endpoint is author-only: enforces auth, ownership, and draft-only
    constraint."""
    ac, article, expected = submit_scenario
    assert (await ac.post(f"/moderation/{article.slug}/submit")).status_code == expected


async def test_submit_transitions_to_pending(
    auth_client: AsyncClient, draft_article: Article
) -> None:
    """Successful submit transitions the article status to pending."""
    assert (await auth_client.post(f"/moderation/{draft_article.slug}/submit")).json()[
        "status"
    ] == "pending"


@pytest.mark.parametrize(
    "submit_scenario",
    [
        pytest.param(("client", "draft_article", 401), id="unauthenticated"),
        pytest.param(("auth_client", "draft_article", 403), id="non-moderator"),
        pytest.param(("mod_auth_client", "pending_article", 409), id="non-draft"),
        pytest.param(("mod_auth_client", "draft_article", 200), id="moderator"),
    ],
    indirect=True,
)
async def test_force_submit(submit_scenario: tuple[AsyncClient, Article, int]) -> None:
    """Force-submit endpoint is moderator-only: enforces auth, role, and draft-only
    constraint."""
    ac, article, expected = submit_scenario
    assert (
        await ac.post(f"/moderation/{article.slug}/force-submit")
    ).status_code == expected


# ── Moderator transition actions ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        pytest.param("approve", "published", id="approve"),
        pytest.param("reject", "rejected", id="reject"),
        pytest.param("request-changes", "draft", id="request-changes"),
    ],
)
async def test_moderator_action_transitions(
    mod_auth_client: AsyncClient,
    pending_article: Article,
    action: str,
    expected_status: str,
) -> None:
    """Each moderator action transitions the article to the correct status."""
    resp = await mod_auth_client.post(f"/moderation/{pending_article.slug}/{action}")
    assert resp.json()["status"] == expected_status


@pytest.mark.parametrize("action", _MOD_ACTIONS)
async def test_moderator_action_requires_moderator(
    auth_client: AsyncClient, pending_article: Article, action: str
) -> None:
    """Contributors cannot perform any moderator action."""
    assert (
        await auth_client.post(f"/moderation/{pending_article.slug}/{action}")
    ).status_code == 403


@pytest.mark.parametrize("action", _MOD_ACTIONS)
async def test_moderator_action_wrong_status(
    mod_auth_client: AsyncClient, draft_article: Article, action: str
) -> None:
    """Moderator actions on a non-pending article return 409."""
    assert (
        await mod_auth_client.post(f"/moderation/{draft_article.slug}/{action}")
    ).status_code == 409


# ── 404 handling ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("action", [*_MOD_ACTIONS, pytest.param("submit", id="submit")])
async def test_moderation_action_not_found(
    mod_auth_client: AsyncClient, action: str
) -> None:
    """All moderation actions on a nonexistent article return 404."""
    assert (
        await mod_auth_client.post(f"/moderation/nonexistent/{action}")
    ).status_code == 404


# ── Backfill on approve ────────────────────────────────────────────────────────


async def test_approve_backfills_wikilink_edges(
    mod_auth_client: AsyncClient,
    db: AsyncSession,
    user: User,
    pending_article: Article,
) -> None:
    """Approving an article backfills wikilink edges in articles that reference it."""
    source = await make_article(
        db,
        user,
        slug="source-org",
        article_type=ArticleType.org,
        metadata_=ORG_META,
        content=f"[[{pending_article.slug}]]",
    )
    await mod_auth_client.post(f"/moderation/{pending_article.slug}/approve")
    rows = await db.execute(
        text(
            "SELECT target_id FROM article_links"
            " WHERE source_id = :sid AND field_name IS NULL"
        ),
        {"sid": source.id},
    )
    assert any(r.target_id == pending_article.id for r in rows)
