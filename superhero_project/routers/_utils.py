"""Shared helpers for article-based routers."""

from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from typing import TypedDict

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import LoaderOption

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType


class ArticleListItem(TypedDict):
    page_name: str
    article_type: ArticleType
    status: ArticleStatus
    metadata: Mapping[str, object]
    tags: list[str]
    updated_at: datetime
    moderator_note: str | None


def article_list_item(article: Article) -> ArticleListItem:
    return {
        "page_name": article.page_name,
        "article_type": article.article_type,
        "status": article.status,
        "metadata": article.metadata_,
        "tags": [t.tag for t in article.tags],
        "updated_at": article.updated_at,
        "moderator_note": article.moderator_note,
    }


async def fetch_article(
    identifier: str,
    db: AsyncSession,
    options: Sequence[LoaderOption] = (),
) -> Article:
    """Look up an article by page_name; raise 404 if absent."""
    stmt = select(Article).where(Article.page_name == identifier)
    if options:
        stmt = stmt.options(*options)
    article = (await db.execute(stmt)).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
