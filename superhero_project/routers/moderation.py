"""Moderation router: submission workflow, queue, and status transitions."""

from datetime import UTC
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project._templates import templates as _templates
from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import Notification
from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.domain.links import backfill_on_publish
from superhero_project.domain.links import build_link_maps
from superhero_project.domain.links import sync_wikilink_edges
from superhero_project.routers._utils import fetch_article

router = APIRouter(prefix="/moderation", tags=["moderation"])


class QueueItemOut(BaseModel):
    """Article shape returned by queue listing and status-transition endpoints."""

    id: int
    page_name: str
    article_type: ArticleType
    metadata: dict[str, Any]
    author_id: int
    author_name: str
    status: ArticleStatus
    created_at: datetime
    updated_at: datetime
    tags: list[str]


def _require_moderator(user: User) -> None:
    """Raise 403 if the user is not a moderator or admin."""
    if user.role not in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=403, detail="Forbidden")


async def _fetch_by_id(article_id: int, db: AsyncSession) -> Article:
    """Fetch an article by primary key with tags and author eagerly loaded."""
    stmt = (
        select(Article)
        .where(Article.id == article_id)
        .options(selectinload(Article.tags), selectinload(Article.author))
    )
    return (await db.execute(stmt)).scalar_one()


def _to_out(article: Article) -> QueueItemOut:
    """Map an ORM Article (tags and author eagerly loaded) to QueueItemOut."""
    return QueueItemOut(
        id=article.id,
        page_name=article.page_name,
        article_type=article.article_type,
        metadata=article.metadata_,
        author_id=article.author_id,
        author_name=article.author.display_name,
        status=article.status,
        created_at=article.created_at,
        updated_at=article.updated_at,
        tags=[t.tag for t in article.tags],
    )


async def _pending_articles(db: AsyncSession) -> list[QueueItemOut]:
    """Return all pending articles ordered by oldest update first."""
    result = await db.execute(
        select(Article)
        .where(Article.status == ArticleStatus.pending)
        .options(selectinload(Article.tags), selectinload(Article.author))
        .order_by(Article.updated_at.asc())
    )
    return [_to_out(a) for a in result.scalars()]


async def _transition(
    identifier: str,
    new_status: ArticleStatus,
    db: AsyncSession,
) -> QueueItemOut:
    """Transition a pending article to new_status."""
    article = await fetch_article(
        identifier, db, [selectinload(Article.tags), selectinload(Article.author)]
    )
    if article.status != ArticleStatus.pending:
        raise HTTPException(status_code=409, detail="Article is not pending")
    article.status = new_status
    await db.commit()
    return _to_out(await _fetch_by_id(article.id, db))


@router.get("/queue", response_model=list[QueueItemOut])
async def get_queue(request: Request, db: DB) -> list[QueueItemOut]:
    """Return all pending articles (moderator/admin only)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    return await _pending_articles(db)


@router.get("/queue/view", response_class=HTMLResponse)
async def queue_view(request: Request, db: DB) -> Response:
    """Render the moderator queue page."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    return _templates.TemplateResponse(
        request=request,
        name="moderation/queue.html",
        context={"articles": await _pending_articles(db), "user": user},
    )


@router.post("/{identifier}/submit")
async def submit_own_article(request: Request, identifier: str, db: DB) -> QueueItemOut:
    """Submit the caller's own draft for moderation review (author only, draft →
    pending)."""
    user = await get_current_user(request, db)
    article = await fetch_article(
        identifier, db, [selectinload(Article.tags), selectinload(Article.author)]
    )
    if user.id != article.author_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if article.status != ArticleStatus.draft:
        raise HTTPException(status_code=409, detail="Article is not a draft")
    article.status = ArticleStatus.pending
    await db.commit()
    return _to_out(await _fetch_by_id(article.id, db))


@router.post("/{identifier}/force-submit")
async def moderator_submit_article(
    request: Request, identifier: str, db: DB
) -> QueueItemOut:
    """Force-submit any draft for moderation review (moderator/admin only, draft →
    pending)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    article = await fetch_article(
        identifier, db, [selectinload(Article.tags), selectinload(Article.author)]
    )
    if article.status != ArticleStatus.draft:
        raise HTTPException(status_code=409, detail="Article is not a draft")
    article.status = ArticleStatus.pending
    await db.commit()
    return _to_out(await _fetch_by_id(article.id, db))


@router.post("/{identifier}/approve")
async def approve_article(request: Request, identifier: str, db: DB) -> QueueItemOut:
    """Approve a pending article (pending → published, moderator/admin only)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    article = await fetch_article(
        identifier, db, [selectinload(Article.tags), selectinload(Article.author)]
    )
    if article.status != ArticleStatus.pending:
        raise HTTPException(status_code=409, detail="Article is not pending")
    article.status = ArticleStatus.published
    article.published_at = datetime.now(UTC).replace(tzinfo=None)
    await backfill_on_publish(article.id, db)
    await db.commit()
    return _to_out(await _fetch_by_id(article.id, db))


@router.post("/{identifier}/reject")
async def reject_article(request: Request, identifier: str, db: DB) -> QueueItemOut:
    """Reject a pending article (pending → rejected, moderator/admin only)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    return await _transition(identifier, ArticleStatus.rejected, db)


class RequestChangesBody(BaseModel):
    """Optional moderator note attached when requesting changes."""

    note: str | None = None


@router.post("/{identifier}/request-changes")
async def request_changes(
    request: Request, identifier: str, body: RequestChangesBody, db: DB
) -> QueueItemOut:
    """Send a pending article back to the author for revision with an optional note
    (pending → draft, moderator/admin only)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    article = await fetch_article(
        identifier, db, [selectinload(Article.tags), selectinload(Article.author)]
    )
    if article.status != ArticleStatus.pending:
        raise HTTPException(status_code=409, detail="Article is not pending")
    article.status = ArticleStatus.draft
    note = body.note.strip() if body.note else None
    article.moderator_note = note
    message = (
        f"Changes requested on {article.page_name}: {note}"
        if note
        else f"Changes requested on {article.page_name}."
    )
    db.add(
        Notification(
            user_id=article.author_id,
            type="changes_requested",
            article_id=article.id,
            message=message,
        )
    )
    await db.commit()
    return _to_out(await _fetch_by_id(article.id, db))


class DisambiguationCreate(BaseModel):
    """Request body for creating a disambiguation article."""

    page_name: str
    content: str = ""


@router.post("/disambiguation", status_code=201)
async def create_disambiguation_article(
    request: Request, body: DisambiguationCreate, db: DB
) -> QueueItemOut:
    """Create and immediately publish a disambiguation article (moderator/admin only).

    Disambiguation articles bypass the normal draft → pending → published flow.
    """
    user = await get_current_user(request, db)
    _require_moderator(user)
    article = Article(
        page_name=body.page_name,
        article_type=ArticleType.disambiguation,
        metadata_={},
        content=body.content,
        author_id=user.id,
        status=ArticleStatus.published,
        published_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(article)
    await db.flush()
    await db.commit()
    index, _ = await build_link_maps(db)
    await sync_wikilink_edges(article.id, article.content, index, db)
    await backfill_on_publish(article.id, db)
    await db.commit()
    return _to_out(await _fetch_by_id(article.id, db))
