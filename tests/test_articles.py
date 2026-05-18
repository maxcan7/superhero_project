"""Tests for article HTML views, JSON API, Markdown rendering, and edit history."""

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import Comment
from superhero_project.db.models import User
from superhero_project.db.models import Vote

pytestmark = pytest.mark.anyio


# ── Markdown render endpoint ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("content", "expected_tag"),
    [
        pytest.param("# Heading", "<h1>", id="heading"),
        pytest.param("**bold**", "<strong>", id="bold"),
        pytest.param("plain text", "<p>", id="paragraph"),
    ],
)
async def test_render_produces_html(
    client: AsyncClient, content: str, expected_tag: str
) -> None:
    """POST /articles/render converts Markdown constructs to the expected HTML tag."""
    resp = await client.post("/articles/render", json={"content": content})
    assert resp.status_code == 200
    assert expected_tag in resp.text


async def test_render_empty(client: AsyncClient) -> None:
    """POST /articles/render with empty content returns empty HTML."""
    resp = await client.post("/articles/render", json={"content": ""})
    assert resp.status_code == 200
    assert resp.text.strip() == ""


# ── JSON API ───────────────────────────────────────────────────────────────────


async def test_get_article_json(
    client: AsyncClient, published_article: Article
) -> None:
    """GET /articles/{id} returns the article as JSON with a rendered body."""
    resp = await client.get(f"/articles/{published_article.slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == published_article.slug
    assert "<h1>" in data["rendered_body"]


# ── Create article ─────────────────────────────────────────────────────────────


async def test_create_article_non_profile(auth_client: AsyncClient) -> None:
    """POST /articles/ creates a draft lore article and returns 201."""
    resp = await auth_client.post(
        "/articles/",
        json={"article_type": "lore", "slug": "origin-of-powers", "tags": ["history"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "origin-of-powers"
    assert data["status"] == "draft"
    assert data["tags"] == ["history"]


@pytest.mark.parametrize(
    ("tags", "expected_tags"),
    [
        pytest.param([], set(), id="no-tags"),
        pytest.param(["hero", "speedster"], {"hero", "speedster"}, id="with-tags"),
    ],
)
async def test_create_profile_auto_assigns_designation(
    auth_client: AsyncClient,
    tags: list[str],
    expected_tags: set[str],
) -> None:
    """POST /articles/ with profile type auto-assigns a CAPE designation as slug."""
    resp = await auth_client.post(
        "/articles/",
        json={
            "article_type": "profile",
            "metadata": {
                "aliases": [],
                "affiliation": [],
                "powers": [],
                "status": "active",
                "base_of_operations": None,
                "first_appearance": None,
            },
            "tags": tags,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["designation"].startswith("CAPE-")
    assert data["slug"] == data["designation"]
    assert set(data["tags"]) == expected_tags


async def test_create_article_invalid_metadata(auth_client: AsyncClient) -> None:
    """POST /articles/ with metadata that fails schema validation returns 422."""
    resp = await auth_client.post(
        "/articles/",
        json={"article_type": "profile", "metadata": {"not_a_field": True}},
    )
    assert resp.status_code == 422


# ── Update article ─────────────────────────────────────────────────────────────

_PROFILE_META = {
    "aliases": ["Updated"],
    "affiliation": [],
    "powers": ["speed"],
    "status": "active",
    "base_of_operations": None,
    "first_appearance": None,
}


@pytest.mark.parametrize(
    ("body", "field", "expected"),
    [
        pytest.param({"content": "## Updated"}, "content", "## Updated", id="content"),
        pytest.param({"tags": ["updated-tag"]}, "tags", ["updated-tag"], id="tags"),
        pytest.param(
            {"metadata": _PROFILE_META}, "metadata", _PROFILE_META, id="metadata"
        ),
    ],
)
async def test_update_article(
    auth_client: AsyncClient,
    published_article: Article,
    body: dict,
    field: str,
    expected: object,
) -> None:
    """PUT /articles/{id} updates content, tags, or metadata and returns the new
    state."""
    resp = await auth_client.put(f"/articles/{published_article.slug}", json=body)
    assert resp.status_code == 200
    assert resp.json()[field] == expected


# ── Delete article ─────────────────────────────────────────────────────────────


async def test_delete_article(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """DELETE /articles/{id} by the author returns 204."""
    resp = await auth_client.delete(f"/articles/{published_article.slug}")
    assert resp.status_code == 204


# ── Access control (unauthenticated → 401, non-author → 403) ──────────────────


@pytest.mark.parametrize(
    ("method", "url_tmpl", "body"),
    [
        pytest.param(
            "post", "/articles/", {"article_type": "lore", "slug": "test"}, id="create"
        ),
        pytest.param("put", "/articles/{slug}", {"content": "## Nope"}, id="update"),
        pytest.param("delete", "/articles/{slug}", None, id="delete"),
    ],
)
async def test_protected_route_requires_session(
    client: AsyncClient,
    published_article: Article,
    method: str,
    url_tmpl: str,
    body: dict | None,
) -> None:
    """Unauthenticated requests to write endpoints return 401."""
    url = url_tmpl.format(slug=published_article.slug)
    kwargs = {"json": body} if body is not None else {}
    resp = await getattr(client, method)(url, **kwargs)
    assert resp.status_code == 401


@pytest.mark.parametrize(
    ("method", "body"),
    [
        pytest.param("put", {"content": "## Hacked"}, id="update"),
        pytest.param("delete", None, id="delete"),
    ],
)
async def test_write_route_forbidden_for_non_author(
    other_auth_client: AsyncClient,
    published_article: Article,
    method: str,
    body: dict | None,
) -> None:
    """Write requests on an article owned by another user return 403."""
    kwargs = {"json": body} if body is not None else {}
    resp = await getattr(other_auth_client, method)(
        f"/articles/{published_article.slug}", **kwargs
    )
    assert resp.status_code == 403


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


# ── Index page ─────────────────────────────────────────────────────────────────


async def test_index_empty(client: AsyncClient) -> None:
    """Index shows the empty state when there are no published articles."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "No published articles yet" in resp.text


@pytest.mark.parametrize(
    ("use_auth", "expected_text"),
    [
        pytest.param(False, "CAPE-0001", id="anonymous"),
        pytest.param(True, "Test User", id="logged-in"),
    ],
)
async def test_index_with_article(
    client: AsyncClient,
    auth_client: AsyncClient,
    published_article: Article,
    use_auth: bool,
    expected_text: str,
) -> None:
    """Index lists published articles; logged-in user also sees their display name."""
    c = auth_client if use_auth else client
    resp = await c.get("/")
    assert resp.status_code == 200
    assert expected_text in resp.text


# ── Article history ────────────────────────────────────────────────────────────


@pytest.fixture
async def edited_article(
    auth_client: AsyncClient, published_article: Article
) -> Article:
    """Published article that has been edited once, creating one history entry."""
    await auth_client.put(f"/articles/{published_article.slug}", json={"content": "v2"})
    return published_article


@pytest.mark.parametrize(
    "url_tmpl",
    [
        pytest.param("/articles/{slug}/history", id="json"),
        pytest.param("/articles/{slug}/history/view", id="html"),
    ],
)
async def test_history_not_found(client: AsyncClient, url_tmpl: str) -> None:
    """Both history endpoints return 404 for a nonexistent article."""
    assert (await client.get(url_tmpl.format(slug="nonexistent"))).status_code == 404


async def test_history_empty(client: AsyncClient, published_article: Article) -> None:
    """Returns an empty list before any edits have been made."""
    assert (
        await client.get(f"/articles/{published_article.slug}/history")
    ).json() == []


async def test_history_records_edits(
    auth_client: AsyncClient, edited_article: Article
) -> None:
    """A second edit produces a second history entry (covers inter-snapshot diff
    path)."""
    await auth_client.put(f"/articles/{edited_article.slug}", json={"content": "v3"})
    assert (
        len((await auth_client.get(f"/articles/{edited_article.slug}/history")).json())
        == 2
    )


async def test_history_diff_shows_change(
    auth_client: AsyncClient, edited_article: Article
) -> None:
    """The content diff contains the text introduced by the edit."""
    history = (await auth_client.get(f"/articles/{edited_article.slug}/history")).json()
    assert "v2" in history[0]["content_diff"]


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
