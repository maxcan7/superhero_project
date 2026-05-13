"""Articles router: CRUD, designation/slug routing, and Markdown rendering."""

import re
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Annotated
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from markdown_it import MarkdownIt
from pydantic import BaseModel
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleHistory
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.db.session import AsyncSessionLocal
from superhero_project.domain.event import EventMetadata
from superhero_project.domain.location import LocationMetadata
from superhero_project.domain.lore import LoreMetadata
from superhero_project.domain.org import OrgMetadata
from superhero_project.domain.profile import ProfileMetadata
from superhero_project.domain.tech import TechMetadata

_md = MarkdownIt()
_CAPE_RE = re.compile(r"^CAPE-\d{4,}$")

router = APIRouter(prefix="/articles", tags=["articles"])

_METADATA_SCHEMAS: dict[ArticleType, type[BaseModel]] = {
    ArticleType.profile: ProfileMetadata,
    ArticleType.event: EventMetadata,
    ArticleType.org: OrgMetadata,
    ArticleType.location: LocationMetadata,
    ArticleType.tech: TechMetadata,
    ArticleType.lore: LoreMetadata,
}


class ArticleCreate(BaseModel):
    """Request body for article creation.

    `slug` is ignored for profiles; the designation (CAPE-XXXX) is auto-assigned from
    the DB-allocated id.
    """

    article_type: ArticleType
    slug: str = ""
    metadata: dict[str, Any] = {}
    content: str = ""
    tags: list[str] = []


class ArticleUpdate(BaseModel):
    """Partial update — only provided fields are applied."""

    metadata: dict[str, Any] | None = None
    content: str | None = None
    tags: list[str] | None = None


class ArticleOut(BaseModel):
    """API response shape for an article.

    `rendered_body` is `content` rendered from Markdown to HTML.
    """

    id: int
    slug: str
    article_type: ArticleType
    designation: str | None
    schema_version: int
    metadata: dict[str, Any]
    content: str
    rendered_body: str
    author_id: int
    status: ArticleStatus
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    tags: list[str]


async def _db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that opens one AsyncSession per request."""

    async with AsyncSessionLocal() as db:
        yield db


DB = Annotated[AsyncSession, Depends(_db_session)]


def _render(text: str) -> str:
    return str(_md.render(text))


def _validate_metadata(
    article_type: ArticleType, data: dict[str, Any]
) -> dict[str, Any]:
    """Dispatch to the per-type Pydantic schema and raise 422 on failure."""
    try:
        return _METADATA_SCHEMAS[article_type](**data).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


async def _get_user(request: Request, db: AsyncSession) -> User:
    """Resolve the session user_id to a User row, raising 401 if absent or stale."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _can_edit(user: User, article: Article) -> bool:
    """True if the user authored the article or holds an elevated role."""
    return user.id == article.author_id or user.role in (
        UserRole.moderator,
        UserRole.admin,
    )


def _to_out(article: Article) -> ArticleOut:
    """Map an ORM Article (tags eagerly loaded) to ArticleOut.

    Renders article content from Markdown to HTML.
    """
    return ArticleOut(
        id=article.id,
        slug=article.slug,
        article_type=article.article_type,
        designation=article.designation,
        schema_version=article.schema_version,
        metadata=article.metadata_,
        content=article.content,
        rendered_body=_render(article.content),
        author_id=article.author_id,
        status=article.status,
        created_at=article.created_at,
        updated_at=article.updated_at,
        published_at=article.published_at,
        tags=[t.tag for t in article.tags],
    )


async def _fetch(identifier: str, db: AsyncSession) -> Article:
    """Look up by designation for CAPE-XXXX identifiers, by slug for all others."""
    col = Article.designation if _CAPE_RE.match(identifier) else Article.slug
    stmt = select(Article).where(col == identifier).options(selectinload(Article.tags))
    article = (await db.execute(stmt)).scalar_one_or_none()
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("/", status_code=201)
async def create_article(request: Request, body: ArticleCreate, db: DB) -> ArticleOut:
    """Create a new article as a draft.

    Profiles are inserted with a UUID tmp slug so the CAPE designation can be derived
    from the DB-assigned id before the transaction commits.
    """
    user = await _get_user(request, db)
    validated_meta = _validate_metadata(body.article_type, body.metadata)
    is_profile = body.article_type == ArticleType.profile

    article = Article(
        slug=f"_tmp_{uuid.uuid4().hex}" if is_profile else body.slug,
        article_type=body.article_type,
        metadata_=validated_meta,
        content=body.content,
        author_id=user.id,
        status=ArticleStatus.draft,
    )
    db.add(article)
    await db.flush()

    if is_profile:
        designation = f"CAPE-{article.id:04d}"
        article.designation = designation
        article.slug = designation

    for tag in body.tags:
        db.add(ArticleTag(article_id=article.id, tag=tag))

    await db.commit()

    result = await db.execute(
        select(Article)
        .where(Article.id == article.id)
        .options(selectinload(Article.tags))
    )
    return _to_out(result.scalar_one())


@router.get("/{identifier}")
async def get_article(identifier: str, db: DB) -> ArticleOut:
    """Fetch a single article by designation or slug."""
    return _to_out(await _fetch(identifier, db))


@router.put("/{identifier}")
async def update_article(
    request: Request, identifier: str, body: ArticleUpdate, db: DB
) -> ArticleOut:
    """Update an article, snapshotting the prior state to ArticleHistory first."""
    user = await _get_user(request, db)
    article = await _fetch(identifier, db)

    if not _can_edit(user, article):
        raise HTTPException(status_code=403, detail="Forbidden")

    db.add(
        ArticleHistory(
            article_id=article.id,
            editor_id=user.id,
            metadata_snapshot=article.metadata_,
            content_snapshot=article.content,
        )
    )

    if body.metadata is not None:
        article.metadata_ = _validate_metadata(article.article_type, body.metadata)
    if body.content is not None:
        article.content = body.content
    if body.tags is not None:
        for existing_tag in article.tags:
            await db.delete(existing_tag)
        for tag in body.tags:
            db.add(ArticleTag(article_id=article.id, tag=tag))

    await db.commit()

    result = await db.execute(
        select(Article)
        .where(Article.id == article.id)
        .options(selectinload(Article.tags))
    )
    return _to_out(result.scalar_one())


@router.delete("/{identifier}", status_code=204)
async def delete_article(request: Request, identifier: str, db: DB) -> None:
    """Delete an article.

    Only the author or a moderator/admin may do this.
    """
    user = await _get_user(request, db)
    article = await _fetch(identifier, db)

    if not _can_edit(user, article):
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(article)
    await db.commit()
