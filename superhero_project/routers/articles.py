"""Articles router: CRUD, designation/slug routing, and Markdown rendering."""

import difflib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from pydantic import BaseModel
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleHistory
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import ArticleType
from superhero_project.db.models import Comment
from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.db.models import Vote
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.dependencies import get_current_user_opt
from superhero_project.domain.event import EventMetadata
from superhero_project.domain.location import LocationMetadata
from superhero_project.domain.lore import LoreMetadata
from superhero_project.domain.org import OrgMetadata
from superhero_project.domain.profile import ProfileMetadata
from superhero_project.domain.tech import TechMetadata
from superhero_project.routers._utils import fetch_article

_md = MarkdownIt()
_templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(prefix="/articles", tags=["articles"])

_METADATA_SCHEMAS: dict[ArticleType, type[BaseModel]] = {
    ArticleType.profile: ProfileMetadata,
    ArticleType.event: EventMetadata,
    ArticleType.org: OrgMetadata,
    ArticleType.location: LocationMetadata,
    ArticleType.tech: TechMetadata,
    ArticleType.lore: LoreMetadata,
}


class ArticleCreate(BaseModel):
    """Request body for article creation."""

    article_type: ArticleType
    slug: str = ""
    metadata: dict[str, Any] = {}
    content: str = ""
    tags: list[str] = []


class ArticleUpdate(BaseModel):
    """Partial update — only provided fields are applied."""

    metadata: dict[str, Any] | None = None
    content: str | None = None
    tags: list[str] | None = None


class ArticleOut(BaseModel):
    """API response shape for an article.

    `rendered_body` is `content` rendered from Markdown to HTML.
    """

    id: int
    slug: str
    article_type: ArticleType
    designation: str | None
    schema_version: int
    metadata: dict[str, Any]
    content: str
    rendered_body: str
    author_id: int
    status: ArticleStatus
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    tags: list[str]


def _render(text: str) -> str:
    """Render a Markdown string to HTML."""
    return str(_md.render(text))


def _validate_metadata(
    article_type: ArticleType, data: dict[str, Any]
) -> dict[str, Any]:
    """Dispatch to the per-type Pydantic schema and raise 422 on failure."""
    try:
        return _METADATA_SCHEMAS[article_type](**data).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _can_edit(user: User, article: Article) -> bool:
    """True if the user authored the article or holds an elevated role."""
    return user.id == article.author_id or user.role in (
        UserRole.moderator,
        UserRole.admin,
    )


def _to_out(article: Article) -> ArticleOut:
    """Map an ORM Article (tags eagerly loaded) to ArticleOut.

    Renders article content from Markdown to HTML.
    """
    return ArticleOut(
        id=article.id,
        slug=article.slug,
        article_type=article.article_type,
        designation=article.designation,
        schema_version=article.schema_version,
        metadata=article.metadata_,
        content=article.content,
        rendered_body=_render(article.content),
        author_id=article.author_id,
        status=article.status,
        created_at=article.created_at,
        updated_at=article.updated_at,
        published_at=article.published_at,
        tags=[t.tag for t in article.tags],
    )


class HistoryEntryOut(BaseModel):
    """Single history entry with a unified diff of content changes."""

    id: int
    editor_id: int
    editor_name: str
    edited_at: datetime
    content_diff: str


def _content_diff(before: str, after: str) -> str:
    """Return a unified diff string between two content snapshots."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(before_lines, after_lines))


async def _load_vote_context(
    article_id: int, user: User | None, db: AsyncSession
) -> tuple[int, int, int, int | None]:
    """Return (upvotes, downvotes, score, user_vote) for an article."""
    all_votes = (
        (await db.execute(select(Vote).where(Vote.article_id == article_id)))
        .scalars()
        .all()
    )
    upvotes = sum(1 for v in all_votes if v.value > 0)
    downvotes = sum(1 for v in all_votes if v.value < 0)
    user_vote: int | None = None
    if user is not None:
        uv = (
            await db.execute(
                select(Vote).where(
                    Vote.article_id == article_id, Vote.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        user_vote = uv.value if uv else None
    return upvotes, downvotes, upvotes - downvotes, user_vote


async def _load_comments(article_id: int, db: AsyncSession) -> list[dict[str, object]]:
    """Return comment dicts for an article, oldest first."""
    rows = (
        (
            await db.execute(
                select(Comment)
                .where(Comment.article_id == article_id)
                .options(selectinload(Comment.author))
                .order_by(Comment.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": c.id,
            "author_id": c.author_id,
            "author_name": c.author.display_name,
            "body": c.body,
            "created_at": c.created_at,
        }
        for c in rows
    ]


async def _load_history(article: Article, db: AsyncSession) -> list[ArticleHistory]:
    """Fetch all history records for an article, ordered oldest first."""
    return list(
        (
            await db.execute(
                select(ArticleHistory)
                .where(ArticleHistory.article_id == article.id)
                .options(selectinload(ArticleHistory.editor))
                .order_by(ArticleHistory.edited_at.asc())
            )
        )
        .scalars()
        .all()
    )


def _compute_diffs(
    records: list[ArticleHistory], current_content: str
) -> list[HistoryEntryOut]:
    """Build HistoryEntryOut list by diffing each snapshot against the next."""
    result = []
    for i, entry in enumerate(records):
        after = (
            records[i + 1].content_snapshot if i + 1 < len(records) else current_content
        )
        result.append(
            HistoryEntryOut(
                id=entry.id,
                editor_id=entry.editor_id,
                editor_name=entry.editor.display_name,
                edited_at=entry.edited_at,
                content_diff=_content_diff(entry.content_snapshot, after),
            )
        )
    return result


class RenderRequest(BaseModel):
    """Request body for the Markdown render helper."""

    content: str


@router.post("/render", response_class=HTMLResponse)
async def render_markdown(body: RenderRequest) -> Response:
    """Render a Markdown string to HTML — used by the live editor preview."""
    return HTMLResponse(_render(body.content))


async def _create_profile(
    body: ArticleCreate, user: User, db: AsyncSession
) -> ArticleOut:
    """Insert a profile with a temp UUID slug, then fix slug/designation from the DB
    id."""
    validated_meta = _validate_metadata(body.article_type, body.metadata)
    article = Article(
        slug=f"_tmp_{uuid.uuid4().hex}",
        article_type=body.article_type,
        metadata_=validated_meta,
        content=body.content,
        author_id=user.id,
        status=ArticleStatus.draft,
    )
    db.add(article)
    await db.flush()
    designation = f"CAPE-{article.id:04d}"
    article.designation = designation
    article.slug = designation
    for tag in body.tags:
        db.add(ArticleTag(article_id=article.id, tag=tag))
    await db.commit()
    result = await db.execute(
        select(Article)
        .where(Article.id == article.id)
        .options(selectinload(Article.tags))
    )
    return _to_out(result.scalar_one())


@router.post("/", status_code=201)
async def create_article(request: Request, body: ArticleCreate, db: DB) -> ArticleOut:
    """Create a new article as a draft."""
    user = await get_current_user(request, db)
    if body.article_type == ArticleType.profile:
        return await _create_profile(body, user, db)
    validated_meta = _validate_metadata(body.article_type, body.metadata)
    article = Article(
        slug=body.slug,
        article_type=body.article_type,
        metadata_=validated_meta,
        content=body.content,
        author_id=user.id,
        status=ArticleStatus.draft,
    )
    db.add(article)
    await db.flush()
    for tag in body.tags:
        db.add(ArticleTag(article_id=article.id, tag=tag))
    await db.commit()
    result = await db.execute(
        select(Article)
        .where(Article.id == article.id)
        .options(selectinload(Article.tags))
    )
    return _to_out(result.scalar_one())


@router.get("/new", response_class=HTMLResponse)
async def new_article_form(request: Request, db: DB) -> Response:
    """Render the article creation editor."""
    user = await get_current_user(request, db)
    return _templates.TemplateResponse(
        request=request,
        name="editor.html",
        context={"user": user, "article": None, "identifier": None},
    )


@router.get("/search", response_class=HTMLResponse)
async def search_form(request: Request, db: DB) -> Response:
    """Render the search form."""
    user = await get_current_user_opt(request, db)
    return _templates.TemplateResponse(
        request=request, name="search.html", context={"user": user, "results": None}
    )


@router.get("/search/results", response_class=HTMLResponse)
async def search_articles(request: Request, db: DB, q: str) -> Response:
    """Full-text search over published articles, ranked by relevance."""
    tsquery = func.plainto_tsquery("english", q)
    stmt = (
        select(Article)
        .where(
            Article.status == ArticleStatus.published,
            Article.search_vector.op("@@")(tsquery),
        )
        .order_by(func.ts_rank(Article.search_vector, tsquery).desc())
        .options(selectinload(Article.tags))
    )
    results = [_to_out(a) for a in (await db.execute(stmt)).scalars().all()]
    user = await get_current_user_opt(request, db)
    return _templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"q": q, "results": results, "user": user},
    )


@router.get("/{identifier}")
async def get_article(identifier: str, db: DB) -> ArticleOut:
    """Fetch a single article by designation or slug."""
    return _to_out(await fetch_article(identifier, db, [selectinload(Article.tags)]))


@router.put("/{identifier}")
async def update_article(
    request: Request, identifier: str, body: ArticleUpdate, db: DB
) -> ArticleOut:
    """Update an article, snapshotting the prior state to ArticleHistory first."""
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])

    if not _can_edit(user, article):
        raise HTTPException(status_code=403, detail="Forbidden")

    db.add(
        ArticleHistory(
            article_id=article.id,
            editor_id=user.id,
            metadata_snapshot=article.metadata_,
            content_snapshot=article.content,
        )
    )

    if body.metadata is not None:
        article.metadata_ = _validate_metadata(article.article_type, body.metadata)
    if body.content is not None:
        article.content = body.content
    if body.tags is not None:
        await db.execute(delete(ArticleTag).where(ArticleTag.article_id == article.id))
        db.expire(article, ["tags"])
        db.add_all([ArticleTag(article_id=article.id, tag=tag) for tag in body.tags])

    await db.commit()

    result = await db.execute(
        select(Article)
        .where(Article.id == article.id)
        .options(selectinload(Article.tags))
    )
    return _to_out(result.scalar_one())


@router.get("/{identifier}/view", response_class=HTMLResponse)
async def view_article_html(request: Request, identifier: str, db: DB) -> Response:
    """Render an article as an HTML page."""
    user = await get_current_user_opt(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    article = _to_out(article_db)
    vote_upvotes, vote_downvotes, vote_score, user_vote = await _load_vote_context(
        article_db.id, user, db
    )
    return _templates.TemplateResponse(
        request=request,
        name="article.html",
        context={
            "article": article,
            "user": user,
            "can_edit": user is not None and _can_edit(user, article_db),
            "is_author": user is not None and user.id == article_db.author_id,
            "vote_upvotes": vote_upvotes,
            "vote_downvotes": vote_downvotes,
            "vote_score": vote_score,
            "user_vote": user_vote,
            "comments": await _load_comments(article_db.id, db),
        },
    )


@router.get("/{identifier}/history")
async def get_article_history(identifier: str, db: DB) -> list[HistoryEntryOut]:
    """Return the edit history for an article, oldest first, each with a content
    diff."""
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])
    return _compute_diffs(await _load_history(article, db), article.content)


@router.get("/{identifier}/history/view", response_class=HTMLResponse)
async def view_article_history(request: Request, identifier: str, db: DB) -> Response:
    """Render the edit history page with unified diffs for each revision."""
    user = await get_current_user_opt(request, db)
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])
    return _templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "article": _to_out(article),
            "history": _compute_diffs(
                await _load_history(article, db), article.content
            ),
            "user": user,
        },
    )


@router.get("/{identifier}/edit", response_class=HTMLResponse)
async def edit_article_form(request: Request, identifier: str, db: DB) -> Response:
    """Render the article editor pre-populated with existing data."""
    user = await get_current_user(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    if not _can_edit(user, article_db):
        raise HTTPException(status_code=403, detail="Forbidden")
    article = _to_out(article_db)
    return _templates.TemplateResponse(
        request=request,
        name="editor.html",
        context={
            "user": user,
            "article": article,
            "identifier": article.designation or article.slug,
        },
    )


@router.delete("/{identifier}", status_code=204)
async def delete_article(request: Request, identifier: str, db: DB) -> None:
    """Delete an article.

    Only the author or a moderator/admin may do this.
    """
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])

    if not _can_edit(user, article):
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(article)
    await db.commit()
