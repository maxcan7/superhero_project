"""Tests for the articles JSON API and Markdown rendering."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.domain.links import sync_wikilink_edges
from tests.utils import ORG_META
from tests.utils import make_article

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
    resp = await client.get(f"/articles/{published_article.page_name}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_name"] == published_article.page_name
    assert "<h1>" in data["rendered_body"]


# ── Create article ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("body", "expected_status"),
    [
        pytest.param(
            {
                "article_type": "lore",
                "page_name": "origin-of-powers",
                "tags": ["history"],
            },
            201,
            id="valid-lore",
        ),
        pytest.param(
            {
                "article_type": "profile",
                "page_name": "bad-meta",
                "metadata": {"not_a_field": True},
            },
            422,
            id="invalid-metadata",
        ),
        pytest.param(
            {"article_type": "disambiguation", "page_name": "mercury"},
            403,
            id="disambiguation-rejected",
        ),
    ],
)
async def test_create_article_status(
    auth_client: AsyncClient, body: dict, expected_status: int
) -> None:
    """POST /articles/ returns the expected status for valid, invalid, and restricted
    bodies."""
    resp = await auth_client.post("/articles/", json=body)
    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("tags", "expected_tags"),
    [
        pytest.param([], set(), id="no-tags"),
        pytest.param(["hero", "speedster"], {"hero", "speedster"}, id="with-tags"),
    ],
)
async def test_create_profile_with_explicit_page_name(
    auth_client: AsyncClient,
    tags: list[str],
    expected_tags: set[str],
) -> None:
    """POST /articles/ with profile type uses the provided page_name."""
    resp = await auth_client.post(
        "/articles/",
        json={
            "article_type": "profile",
            "page_name": "new-hero",
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
    assert data["page_name"] == "new-hero"
    assert set(data["tags"]) == expected_tags


# ── Update article ─────────────────────────────────────────────────────────────

_PROFILE_META = {
    "aliases": ["updated"],
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
    resp = await auth_client.put(f"/articles/{published_article.page_name}", json=body)
    assert resp.status_code == 200
    assert resp.json()[field] == expected


# ── Delete article ─────────────────────────────────────────────────────────────


async def test_delete_article(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """DELETE /articles/{id} by the author returns 204."""
    resp = await auth_client.delete(f"/articles/{published_article.page_name}")
    assert resp.status_code == 204


# ── Access control (unauthenticated → 401, non-author → 403) ──────────────────


@pytest.mark.parametrize(
    ("method", "url_tmpl", "body"),
    [
        pytest.param(
            "post",
            "/articles/",
            {"article_type": "lore", "page_name": "test"},
            id="create",
        ),
        pytest.param(
            "put", "/articles/{page_name}", {"content": "## Nope"}, id="update"
        ),
        pytest.param("delete", "/articles/{page_name}", None, id="delete"),
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
    url = url_tmpl.format(page_name=published_article.page_name)
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
        f"/articles/{published_article.page_name}", **kwargs
    )
    assert resp.status_code == 403


# ── Index page ─────────────────────────────────────────────────────────────────


async def test_index_empty(client: AsyncClient) -> None:
    """Index shows the empty state when there are no published articles."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "No published articles yet" in resp.text


@pytest.mark.parametrize(
    ("use_auth", "expected_text"),
    [
        pytest.param(False, "the-guardian", id="anonymous"),
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


# ── Article history (JSON) ─────────────────────────────────────────────────────


async def test_history_not_found(client: AsyncClient) -> None:
    """GET /articles/{slug}/history returns 404 for a nonexistent article."""
    assert (await client.get("/articles/nonexistent/history")).status_code == 404


async def test_history_empty(client: AsyncClient, published_article: Article) -> None:
    """Returns an empty list before any edits have been made."""
    assert (
        await client.get(f"/articles/{published_article.page_name}/history")
    ).json() == []


async def test_history_records_edits(
    auth_client: AsyncClient, edited_article: Article
) -> None:
    """A second edit produces a second history entry (covers inter-snapshot diff
    path)."""
    url = f"/articles/{edited_article.page_name}"
    await auth_client.put(url, json={"content": "v3"})
    assert len((await auth_client.get(f"{url}/history")).json()) == 2


async def test_history_diff_shows_change(
    auth_client: AsyncClient, edited_article: Article
) -> None:
    """The content diff contains the text introduced by the edit."""
    url = f"/articles/{edited_article.page_name}/history"
    history = (await auth_client.get(url)).json()
    assert "v2" in history[0]["content_diff"]


# ── Backfill on alias change ───────────────────────────────────────────────────


async def test_update_removed_alias_deletes_edges(
    auth_client: AsyncClient,
    db: AsyncSession,
    user: User,
    published_article: Article,
) -> None:
    """Removing an alias via PUT deletes wikilink edges resolved via that alias."""
    source = await make_article(
        db,
        user,
        page_name="source-org",
        article_type=ArticleType.org,
        metadata_=ORG_META,
        content="[[The Guardian]]",
    )
    await sync_wikilink_edges(
        source.id, source.content, {"the guardian": published_article.id}, db
    )
    await db.commit()
    new_meta = {
        "aliases": [],
        "affiliation": [],
        "powers": ["flight", "strength"],
        "status": "active",
        "base_of_operations": None,
        "first_appearance": None,
    }
    await auth_client.put(
        f"/articles/{published_article.page_name}", json={"metadata": new_meta}
    )
    rows = list(
        (
            await db.execute(
                text(
                    "SELECT target_id FROM article_links"
                    " WHERE source_id = :sid AND field_name IS NULL"
                ),
                {"sid": source.id},
            )
        ).fetchall()
    )
    assert rows == []
