"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that opens one AsyncSession per request."""

    async with AsyncSessionLocal() as db:
        yield db


DB = Annotated[AsyncSession, Depends(get_db)]
