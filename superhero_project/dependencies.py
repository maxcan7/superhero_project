"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import User
from superhero_project.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that opens one AsyncSession per request."""

    async with AsyncSessionLocal() as db:
        yield db


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


DB = Annotated[AsyncSession, Depends(get_db)]
