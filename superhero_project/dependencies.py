"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Notification
from superhero_project.db.models import User
from superhero_project.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that opens one AsyncSession per request."""

    async with AsyncSessionLocal() as db:
        yield db


DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(request: Request, db: AsyncSession) -> User:
    """Resolve the session user_id to a User row, raising 401 if absent or stale."""
    user_id = request.session.get("user_id")
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def get_current_user_opt(request: Request, db: AsyncSession) -> User | None:
    """Resolve the session user_id to a User row, returning None if absent or stale."""
    user_id = request.session.get("user_id")
    return await db.get(User, user_id) if user_id else None


async def inject_unread_count(request: Request, db: DB) -> None:
    """Set request.state.unread_count for the nav badge on every request."""
    user_id = request.session.get("user_id")
    count = 0
    if user_id:
        count = (
            await db.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.user_id == user_id, ~Notification.read)
            )
        ) or 0
    request.state.unread_count = count
