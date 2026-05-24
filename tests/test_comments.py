"""Tests for the comments router: list, create, edit, and delete comments."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import Comment
from superhero_project.db.models import User

pytestmark = pytest.mark.anyio


@pytest.fixture
async def comment(db: AsyncSession, published_article: Article, user: User) -> Comment:
    """A comment on the published article, authored by the primary test user."""
    c = Comment(article_id=published_article.id, author_id=user.id, body="Hello world")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


# ── Auth ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "url_tmpl", "body"),
    [
        pytest.param("post", "/comments/{page_name}", {"body": "hi"}, id="create"),
        pytest.param(
            "put", "/comments/{page_name}/{comment_id}", {"body": "x"}, id="update"
        ),
        pytest.param("delete", "/comments/{page_name}/{comment_id}", None, id="delete"),
    ],
)
async def test_comment_requires_auth(
    client: AsyncClient,
    published_article: Article,
    comment: Comment,
    method: str,
    url_tmpl: str,
    body: dict | None,
) -> None:
    """POST, PUT, and DELETE return 401 without a session."""
    url = url_tmpl.format(page_name=published_article.page_name, comment_id=comment.id)
    kwargs = {"json": body} if body is not None else {}
    assert (await getattr(client, method)(url, **kwargs)).status_code == 401


# ── Not found ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "url_tmpl", "body"),
    [
        pytest.param("get", "/comments/{page_name}", None, id="get"),
        pytest.param("post", "/comments/{page_name}", {"body": "hi"}, id="create"),
        pytest.param("put", "/comments/{page_name}/999", {"body": "x"}, id="update"),
        pytest.param("delete", "/comments/{page_name}/999", None, id="delete"),
    ],
)
async def test_comment_article_not_found(
    auth_client: AsyncClient, method: str, url_tmpl: str, body: dict | None
) -> None:
    """All comment endpoints return 404 for a nonexistent article."""
    url = url_tmpl.format(page_name="nonexistent")
    kwargs = {"json": body} if body is not None else {}
    assert (await getattr(auth_client, method)(url, **kwargs)).status_code == 404


@pytest.mark.parametrize(
    ("method", "body"),
    [
        pytest.param("put", {"body": "x"}, id="update"),
        pytest.param("delete", None, id="delete"),
    ],
)
async def test_comment_not_found(
    auth_client: AsyncClient, published_article: Article, method: str, body: dict | None
) -> None:
    """PUT and DELETE return 404 when the comment id does not exist."""
    kwargs = {"json": body} if body is not None else {}
    assert (
        await getattr(auth_client, method)(
            f"/comments/{published_article.page_name}/999", **kwargs
        )
    ).status_code == 404


# ── Forbidden ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "body"),
    [
        pytest.param("put", {"body": "x"}, id="update"),
        pytest.param("delete", None, id="delete"),
    ],
)
async def test_comment_forbidden_for_non_author(
    other_auth_client: AsyncClient,
    published_article: Article,
    comment: Comment,
    method: str,
    body: dict | None,
) -> None:
    """Non-author receives 403 on PUT and DELETE."""
    kwargs = {"json": body} if body is not None else {}
    assert (
        await getattr(other_auth_client, method)(
            f"/comments/{published_article.page_name}/{comment.id}", **kwargs
        )
    ).status_code == 403


# ── GET ───────────────────────────────────────────────────────────────────────


async def test_list_comments_empty(
    client: AsyncClient, published_article: Article
) -> None:
    """Returns an empty list when no comments exist."""
    assert (await client.get(f"/comments/{published_article.page_name}")).json() == []


async def test_list_comments(
    client: AsyncClient, published_article: Article, comment: Comment
) -> None:
    """Returns existing comments ordered by creation time."""
    data = (await client.get(f"/comments/{published_article.page_name}")).json()
    assert len(data) == 1
    assert data[0]["body"] == comment.body


# ── POST ──────────────────────────────────────────────────────────────────────


async def test_create_comment(
    auth_client: AsyncClient, published_article: Article
) -> None:
    """Creates a comment and returns 201 with the stored body."""
    resp = await auth_client.post(
        f"/comments/{published_article.page_name}", json={"body": "Nice article!"}
    )
    assert resp.status_code == 201
    assert resp.json()["body"] == "Nice article!"


# ── PUT ───────────────────────────────────────────────────────────────────────


async def test_update_comment(
    auth_client: AsyncClient, published_article: Article, comment: Comment
) -> None:
    """Author can update their comment body."""
    data = (
        await auth_client.put(
            f"/comments/{published_article.page_name}/{comment.id}",
            json={"body": "Updated"},
        )
    ).json()
    assert data["body"] == "Updated"


# ── DELETE ────────────────────────────────────────────────────────────────────


async def test_delete_comment(
    auth_client: AsyncClient, published_article: Article, comment: Comment
) -> None:
    """Author can delete their comment; returns 204."""
    assert (
        await auth_client.delete(
            f"/comments/{published_article.page_name}/{comment.id}"
        )
    ).status_code == 204
