"""Comments router: create, edit, delete comments on articles."""

from datetime import datetime

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from superhero_project._limiter import limiter
from superhero_project.config import settings
from superhero_project.db.models import Comment
from superhero_project.db.models import User
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.routers._utils import fetch_article

router = APIRouter(prefix="/comments", tags=["comments"])


class CommentIn(BaseModel):
    """Request body for creating or updating a comment."""

    body: str


class CommentOut(BaseModel):
    """API response shape for a comment."""

    id: int
    article_id: int
    author_id: int
    author_name: str
    body: str
    created_at: datetime
    updated_at: datetime


async def _fetch_comment(comment_id: int, article_id: int, db: AsyncSession) -> Comment:
    """Fetch a comment by ID scoped to an article, raising 404 if not found."""
    stmt = (
        select(Comment)
        .where(Comment.id == comment_id, Comment.article_id == article_id)
        .options(selectinload(Comment.author))
    )
    comment = (await db.execute(stmt)).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment


def _require_comment_author(user: User, comment: Comment) -> None:
    """Raise 403 if the user is not the comment's author."""
    if user.id != comment.author_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def _to_out(comment: Comment) -> CommentOut:
    """Map an ORM Comment (author eagerly loaded) to CommentOut."""
    return CommentOut(
        id=comment.id,
        article_id=comment.article_id,
        author_id=comment.author_id,
        author_name=comment.author.display_name,
        body=comment.body,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.get("/{identifier}")
async def list_comments(identifier: str, db: DB) -> list[CommentOut]:
    """List all comments on an article, ordered by creation time."""
    article = await fetch_article(identifier, db)
    result = await db.execute(
        select(Comment)
        .where(Comment.article_id == article.id)
        .options(selectinload(Comment.author))
        .order_by(Comment.created_at.asc())
    )
    return [_to_out(c) for c in result.scalars()]


@router.post("/{identifier}", status_code=201)
@limiter.limit(settings.rate_limit_comment_create)
async def create_comment(
    request: Request, identifier: str, body: CommentIn, db: DB
) -> CommentOut:
    """Add a comment to an article."""
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db)
    comment = Comment(article_id=article.id, author_id=user.id, body=body.body)
    db.add(comment)
    await db.commit()
    return _to_out(await _fetch_comment(comment.id, article.id, db))


@router.put("/{identifier}/{comment_id}")
async def update_comment(
    request: Request, identifier: str, comment_id: int, body: CommentIn, db: DB
) -> CommentOut:
    """Edit a comment.

    Only the comment author may edit.
    """
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db)
    comment = await _fetch_comment(comment_id, article.id, db)
    _require_comment_author(user, comment)
    comment.body = body.body
    await db.commit()
    return _to_out(await _fetch_comment(comment.id, article.id, db))


@router.delete("/{identifier}/{comment_id}", status_code=204)
async def delete_comment(
    request: Request, identifier: str, comment_id: int, db: DB
) -> None:
    """Delete a comment.

    Only the comment author may delete.
    """
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db)
    comment = await _fetch_comment(comment_id, article.id, db)
    _require_comment_author(user, comment)
    await db.delete(comment)
    await db.commit()
