"""Test utilities."""

import json
from base64 import b64encode
from typing import Any

import itsdangerous
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User


async def make_article(
    db: AsyncSession,
    user: User,
    *,
    slug: str,
    article_type: ArticleType,
    metadata_: dict[str, Any],
    status: ArticleStatus = ArticleStatus.published,
    designation: str | None = None,
    content: str = "",
) -> Article:
    """Persist and return a minimal article for use in tests."""
    a = Article(
        slug=slug,
        article_type=article_type,
        designation=designation,
        metadata_=metadata_,
        content=content,
        author_id=user.id,
        status=status,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


def make_session_cookie(session_data: dict[str, object], secret: str) -> str:
    """Return a Starlette-compatible signed session cookie value."""
    data = b64encode(json.dumps(session_data).encode("utf-8"))
    signer = itsdangerous.TimestampSigner(secret)
    return signer.sign(data).decode("utf-8")
