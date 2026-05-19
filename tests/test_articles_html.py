"""Tests for article HTML view endpoints."""

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleType
from superhero_project.db.models import Comment
from superhero_project.db.models import User
from superhero_project.db.models import Vote
from superhero_project.domain.links import sync_metadata_edges
from superhero_project.domain.links import sync_wikilink_edges
from tests.utils import LOCATION_META
from tests.utils import ORG_META
from tests.utils import PROFILE_META
from tests.utils import make_article

pytestmark = pytest.mark.anyio


# ── Article HTML view ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("use_auth", "expected_texts"),
    [
        pytest.param(False, ["<h1>", "vote-bar", "No comments yet"], id="anonymous"),
        pytest.param(True, ["Test User", "vote-bar"], id="logged-in"),
    ],
)
async def test_article_view(
    client: AsyncClient,
    auth_client: AsyncClient,
    published_article: Article,
    use_auth: bool,
    expected_texts: list[str],
) -> None:
    """Article view returns 200 and renders the vote bar; logged-in user sees their
    name."""
    c = auth_client if use_auth else client
    resp = await c.get(f"/articles/{published_article.slug}/view")
    assert resp.status_code == 200
    for text in expected_texts:
        assert text in resp.text


async def test_article_view_reference_panels(
    client: AsyncClient,
    published_article: Article,
    db: AsyncSession,
    user: User,
) -> None:
    """Both ref-panel group labels appear when wikilink and metadata edges exist."""
    target = await make_article(
        db,
        user,
        slug="gotham",
        article_type=ArticleType.location,
        metadata_=LOCATION_META,
    )
    index = {"gotham": target.id}
    await sync_wikilink_edges(published_article.id, "[[gotham]]", index, db)
    await sync_metadata_edges(
        published_article.id,
        ArticleType.profile,
        {**PROFILE_META, "base_of_operations": "gotham"},
        index,
        db,
    )
    await db.commit()
    resp = await client.get(f"/articles/{published_article.slug}/view")
    assert resp.status_code == 200
    assert "Mentioned in body" in resp.text
    assert "Via: Base Of Operations" in resp.text


async def test_article_view_404(client: AsyncClient) -> None:
    """Article view returns 404 for an unknown identifier."""
    resp = await client.get("/articles/nonexistent/view")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("vote_value", "active_present"),
    [
        pytest.param(None, False, id="no-vote"),
        pytest.param(1, True, id="upvote"),
        pytest.param(-1, True, id="downvote"),
    ],
)
async def test_article_view_vote_state(
    auth_client: AsyncClient,
    published_article: Article,
    db: AsyncSession,
    user: User,
    vote_value: int | None,
    active_present: bool,
) -> None:
    """Active class on vote button reflects the current user's existing vote."""
    if vote_value is not None:
        db.add(Vote(article_id=published_article.id, user_id=user.id, value=vote_value))
        await db.commit()
    resp = await auth_client.get(f"/articles/{published_article.slug}/view")
    assert resp.status_code == 200
    assert ("vote-btn--active" in resp.text) == active_present


@pytest.mark.parametrize(
    ("own_comment", "expect_actions"),
    [
        pytest.param(True, True, id="own"),
        pytest.param(False, False, id="other"),
    ],
)
async def test_article_view_comment_actions(
    auth_client: AsyncClient,
    published_article: Article,
    db: AsyncSession,
    user: User,
    other_user: User,
    own_comment: bool,
    expect_actions: bool,
) -> None:
    """Edit/delete buttons appear iff the logged-in user authored the comment."""
    author = user if own_comment else other_user
    db.add(Comment(article_id=published_article.id, author_id=author.id, body="A note"))
    await db.commit()
    resp = await auth_client.get(f"/articles/{published_article.slug}/view")
    assert resp.status_code == 200
    assert "A note" in resp.text
    assert ("comment-edit-btn" in resp.text) == expect_actions


# ── Article history (HTML) ─────────────────────────────────────────────────────


async def test_history_not_found(client: AsyncClient) -> None:
    """GET /articles/{slug}/history/view returns 404 for a nonexistent article."""
    assert (await client.get("/articles/nonexistent/history/view")).status_code == 404


async def test_history_view_renders(
    auth_client: AsyncClient, edited_article: Article
) -> None:
    """History view page renders the article identifier."""
    assert (
        edited_article.slug
        in (await auth_client.get(f"/articles/{edited_article.slug}/history/view")).text
    )


# ── Search ─────────────────────────────────────────────────────────────────────


@pytest.fixture
async def indexed_article(db: AsyncSession, published_article: Article) -> Article:
    """Published article with search_vector populated (trigger not run by
    create_all)."""
    await db.execute(
        sa.update(Article)
        .where(Article.id == published_article.id)
        .values(search_vector=sa.func.to_tsvector("english", published_article.content))
    )
    await db.commit()
    return published_article


@pytest.mark.parametrize(
    ("use_auth", "expected_text"),
    [
        pytest.param(False, "<form", id="anonymous"),
        pytest.param(True, "Test User", id="logged-in"),
    ],
)
async def test_search_form(
    client: AsyncClient,
    auth_client: AsyncClient,
    use_auth: bool,
    expected_text: str,
) -> None:
    """GET /articles/search renders the search form; logged-in user sees their name."""
    c = auth_client if use_auth else client
    resp = await c.get("/articles/search")
    assert resp.status_code == 200
    assert expected_text in resp.text


@pytest.mark.parametrize(
    ("q", "expected_text"),
    [
        pytest.param("guardian", "CAPE-0001", id="hit"),
        pytest.param("xyznotfound", "No results", id="miss"),
    ],
)
async def test_search_results(
    client: AsyncClient, indexed_article: Article, q: str, expected_text: str
) -> None:
    """GET /articles/search/results?q= returns hits or the empty-state message."""
    resp = await client.get(f"/articles/search/results?q={q}")
    assert resp.status_code == 200
    assert expected_text in resp.text


async def test_search_results_missing_q(client: AsyncClient) -> None:
    """GET /articles/search/results without q returns 422."""
    resp = await client.get("/articles/search/results")
    assert resp.status_code == 422


# ── Editor HTML views ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url_tmpl",
    [
        pytest.param("/articles/new", id="new"),
        pytest.param("/articles/{slug}/edit", id="edit"),
    ],
)
async def test_editor_requires_auth(
    client: AsyncClient, published_article: Article, url_tmpl: str
) -> None:
    """Editor routes return 401 without a session."""
    resp = await client.get(url_tmpl.format(slug=published_article.slug))
    assert resp.status_code == 401


async def test_new_article_form_renders(auth_client: AsyncClient) -> None:
    """GET /articles/new renders the create editor."""
    resp = await auth_client.get("/articles/new")
    assert resp.status_code == 200
    assert 'data-mode="create"' in resp.text


async def test_edit_article_form_access_errors(
    auth_client: AsyncClient,
    other_auth_client: AsyncClient,
    published_article: Article,
) -> None:
    """Edit form returns 403 for a non-owner and 404 for a missing article."""
    assert (
        await other_auth_client.get(f"/articles/{published_article.slug}/edit")
    ).status_code == 403
    assert (await auth_client.get("/articles/nonexistent/edit")).status_code == 404


async def test_edit_article_form_renders(
    auth_client: AsyncClient,
    mod_auth_client: AsyncClient,
    published_article: Article,
) -> None:
    """Edit form is accessible to author and moderator, pre-populated with existing
    data."""
    for c in (auth_client, mod_auth_client):
        resp = await c.get(f"/articles/{published_article.slug}/edit")
        assert resp.status_code == 200
        assert 'data-mode="edit"' in resp.text
        assert "Protector of the city" in resp.text


# ── Org member roster ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("has_member", "expected_text"),
    [
        pytest.param(True, "captain-america", id="with-member"),
        pytest.param(False, "No members found", id="empty"),
    ],
)
async def test_members_page(
    client: AsyncClient,
    db: AsyncSession,
    user: User,
    has_member: bool,
    expected_text: str,
) -> None:
    """Members page renders affiliated profiles or the empty state."""
    org = await make_article(
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=ORG_META
    )
    if has_member:
        profile = await make_article(
            db,
            user,
            slug="captain-america",
            article_type=ArticleType.profile,
            metadata_=PROFILE_META,
        )
        await sync_metadata_edges(
            profile.id,
            ArticleType.profile,
            {**PROFILE_META, "affiliation": ["avengers"]},
            {"avengers": org.id},
            db,
        )
        await db.commit()
    resp = await client.get(f"/articles/{org.slug}/members")
    assert resp.status_code == 200
    assert expected_text in resp.text


async def test_members_page_404(client: AsyncClient) -> None:
    """Members page returns 404 for a nonexistent article."""
    assert (await client.get("/articles/nonexistent/members")).status_code == 404
