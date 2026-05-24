"""Test utilities and shared metadata fixtures."""

import json
from base64 import b64encode
from typing import Any

import itsdangerous
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.domain.comic import ComicMetadata
from superhero_project.domain.disambiguation import DisambiguationMetadata
from superhero_project.domain.event import EventMetadata
from superhero_project.domain.location import LocationMetadata
from superhero_project.domain.lore import LoreMetadata
from superhero_project.domain.org import OrgMetadata
from superhero_project.domain.profile import ProfileMetadata
from superhero_project.domain.tech import TechMetadata

DISAMBIG_META: dict = DisambiguationMetadata().model_dump()

# Representative outgoing-edge dicts (same shape as fetch_outgoing_links rows).
WIKILINK_EDGE: dict[str, str | None] = {
    "page_name": "gotham",
    "article_type": "location",
    "field_name": None,
    "resolved_via": "gotham",
}
GOTHAM_EDGE: dict[str, str | None] = {
    "page_name": "gotham",
    "article_type": "location",
    "field_name": "base_of_operations",
    "resolved_via": "gotham",
}
ORG_META: dict = OrgMetadata().model_dump()
PROFILE_META: dict = ProfileMetadata().model_dump()
EVENT_META: dict = EventMetadata().model_dump()
LOCATION_META: dict = LocationMetadata().model_dump()
TECH_META: dict = TechMetadata().model_dump()
LORE_META: dict = LoreMetadata().model_dump()
COMIC_META: dict = ComicMetadata().model_dump()


async def make_article(
    db: AsyncSession,
    user: User,
    *,
    page_name: str,
    article_type: ArticleType,
    metadata_: dict[str, Any],
    status: ArticleStatus = ArticleStatus.published,
    content: str = "",
) -> Article:
    """Persist and return a minimal article for use in tests."""
    a = Article(
        page_name=page_name,
        article_type=article_type,
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
