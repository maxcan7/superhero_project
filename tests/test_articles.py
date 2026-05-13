"""Tests for article HTML views and the Markdown render endpoint."""

import pytest
from httpx import AsyncClient

from superhero_project.db.models import Article

pytestmark = pytest.mark.anyio


# ── Markdown render endpoint ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("content", "expected_tag"),
    [
        ("# Heading", "<h1>"),
        ("**bold**", "<strong>"),
        ("plain text", "<p>"),
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


# ── Article HTML view ──────────────────────────────────────────────────────────


async def test_article_view(client: AsyncClient, published_article: Article) -> None:
    """Article view returns 200 with the designation and rendered Markdown body."""
    resp = await client.get(f"/articles/{published_article.slug}/view")
    assert resp.status_code == 200
    assert published_article.designation in resp.text
    assert "<h1>" in resp.text


async def test_article_view_404(client: AsyncClient) -> None:
    """Article view returns 404 for an unknown identifier."""
    resp = await client.get("/articles/nonexistent/view")
    assert resp.status_code == 404


# ── Index page ─────────────────────────────────────────────────────────────────


async def test_index_empty(client: AsyncClient) -> None:
    """Index shows the empty state when there are no published articles."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "No published articles yet" in resp.text


async def test_index_lists_published(
    client: AsyncClient, published_article: Article
) -> None:
    """Index lists published articles by slug."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert published_article.slug in resp.text
