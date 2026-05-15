"""Votes router: up/downvote articles, one vote per user per article."""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Vote
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.routers._utils import fetch_article

router = APIRouter(prefix="/votes", tags=["votes"])


class VoteIn(BaseModel):
    """Request body for casting or updating a vote."""

    value: int


class VoteSummary(BaseModel):
    """Aggregate vote counts for an article."""

    article_id: int
    upvotes: int
    downvotes: int
    score: int


async def _vote_summary(article_id: int, db: AsyncSession) -> VoteSummary:
    """Compute up/downvote counts and net score for an article."""
    votes = (
        (await db.execute(select(Vote).where(Vote.article_id == article_id)))
        .scalars()
        .all()
    )
    upvotes = sum(1 for v in votes if v.value > 0)
    downvotes = sum(1 for v in votes if v.value < 0)
    return VoteSummary(
        article_id=article_id,
        upvotes=upvotes,
        downvotes=downvotes,
        score=upvotes - downvotes,
    )


@router.get("/{identifier}")
async def get_votes(identifier: str, db: DB) -> VoteSummary:
    """Return vote totals for an article."""
    article = await fetch_article(identifier, db)
    return await _vote_summary(article.id, db)


async def _upsert_vote(
    user_id: int, article_id: int, value: int, db: AsyncSession
) -> None:
    """Insert a new vote or update the existing one for this user/article pair."""
    existing = (
        await db.execute(
            select(Vote).where(Vote.article_id == article_id, Vote.user_id == user_id)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(Vote(article_id=article_id, user_id=user_id, value=value))
    else:
        existing.value = value


@router.put("/{identifier}")
async def cast_vote(
    request: Request, identifier: str, body: VoteIn, db: DB
) -> VoteSummary:
    """Cast or update a vote (+1 or -1) on an article."""
    user = await get_current_user(request, db)
    if body.value not in (1, -1):
        raise HTTPException(status_code=422, detail="Vote value must be 1 or -1")
    article = await fetch_article(identifier, db)
    await _upsert_vote(user.id, article.id, body.value, db)
    await db.commit()
    return await _vote_summary(article.id, db)


@router.delete("/{identifier}", status_code=204)
async def remove_vote(request: Request, identifier: str, db: DB) -> None:
    """Remove the current user's vote from an article."""
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db)

    vote = (
        await db.execute(
            select(Vote).where(Vote.article_id == article.id, Vote.user_id == user.id)
        )
    ).scalar_one_or_none()

    if vote is None:
        raise HTTPException(status_code=404, detail="Vote not found")

    await db.delete(vote)
    await db.commit()
