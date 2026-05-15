"""Shared helpers for article-based routers."""

import re
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import LoaderOption

from superhero_project.db.models import Article

_CAPE_RE = re.compile(r"^CAPE-\d{4,}$")


async def fetch_article(
    identifier: str,
    db: AsyncSession,
    options: Sequence[LoaderOption] = (),
) -> Article:
    """Look up an article by CAPE designation or slug; raise 404 if absent."""
    col = Article.designation if _CAPE_RE.match(identifier) else Article.slug
    stmt = select(Article).where(col == identifier)
    if options:
        stmt = stmt.options(*options)
    article = (await db.execute(stmt)).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
