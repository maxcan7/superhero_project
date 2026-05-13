"""Tests for shared FastAPI dependencies."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.dependencies import get_db

pytestmark = pytest.mark.anyio


async def test_get_db_yields_session() -> None:
    """get_db opens and yields a usable AsyncSession."""
    gen = get_db()
    db = await anext(gen)
    assert isinstance(db, AsyncSession)
    await gen.aclose()
