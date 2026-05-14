"""Moderation router: submission workflow, queue, and status transitions."""

import re
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user

_CAPE_RE = re.compile(r"^CAPE-\d{4,}$")
_templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(prefix="/moderation", tags=["moderation"])


class QueueItemOut(BaseModel):
    """Article shape returned by queue listing and status-transition endpoints."""

    id: int
    slug: str
    article_type: ArticleType
    designation: str | None
    metadata: dict[str, Any]
    author_id: int
    author_name: str
    status: ArticleStatus
    created_at: datetime
    updated_at: datetime
    tags: list[str]


def _require_moderator(user: User) -> None:
    if user.role not in (UserRole.moderator, UserRole.admin):
        raise HTTPException(status_code=403, detail="Forbidden")


async def _fetch(identifier: str, db: AsyncSession) -> Article:
    col = Article.designation if _CAPE_RE.match(identifier) else Article.slug
    stmt = (
        select(Article)
        .where(col == identifier)
        .options(selectinload(Article.tags), selectinload(Article.author))
    )
    article = (await db.execute(stmt)).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


async def _fetch_by_id(article_id: int, db: AsyncSession) -> Article:
    stmt = (
        select(Article)
        .where(Article.id == article_id)
        .options(selectinload(Article.tags), selectinload(Article.author))
    )
    return (await db.execute(stmt)).scalar_one()


def _to_out(article: Article) -> QueueItemOut:
    return QueueItemOut(
        id=article.id,
        slug=article.slug,
        article_type=article.article_type,
        designation=article.designation,
        metadata=article.metadata_,
        author_id=article.author_id,
        author_name=article.author.display_name,
        status=article.status,
        created_at=article.created_at,
        updated_at=article.updated_at,
        tags=[t.tag for t in article.tags],
    )


async def _pending_articles(db: AsyncSession) -> list[QueueItemOut]:
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
    *,
    set_published_at: bool = False,
) -> QueueItemOut:
    article = await _fetch(identifier, db)
    if article.status != ArticleStatus.pending:
        raise HTTPException(status_code=409, detail="Article is not pending")
    article.status = new_status
    if set_published_at:
        article.published_at = datetime.now(UTC).replace(tzinfo=None)
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
async def submit_article(request: Request, identifier: str, db: DB) -> QueueItemOut:
    """Submit a draft article for moderation review (draft → pending)."""
    user = await get_current_user(request, db)
    article = await _fetch(identifier, db)
    if user.id != article.author_id and user.role not in (
        UserRole.moderator,
        UserRole.admin,
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
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
    return await _transition(
        identifier, ArticleStatus.published, db, set_published_at=True
    )


@router.post("/{identifier}/reject")
async def reject_article(request: Request, identifier: str, db: DB) -> QueueItemOut:
    """Reject a pending article (pending → rejected, moderator/admin only)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    return await _transition(identifier, ArticleStatus.rejected, db)


@router.post("/{identifier}/request-changes")
async def request_changes(request: Request, identifier: str, db: DB) -> QueueItemOut:
    """Send a pending article back to the author for revision (pending → draft,
    moderator/admin only)."""
    user = await get_current_user(request, db)
    _require_moderator(user)
    return await _transition(identifier, ArticleStatus.draft, db)
