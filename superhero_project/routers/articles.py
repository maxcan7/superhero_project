"""Articles router: CRUD, page_name routing, and Markdown rendering."""

import difflib
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from markdown_it import MarkdownIt
from pydantic import BaseModel
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleHistory
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.domain.comic import ComicMetadata
from superhero_project.domain.disambiguation import DisambiguationMetadata
from superhero_project.domain.event import EventMetadata
from superhero_project.domain.links import AliasIndex
from superhero_project.domain.links import PageNameMap
from superhero_project.domain.links import backfill_on_alias_change
from superhero_project.domain.links import build_link_maps
from superhero_project.domain.links import render_wikilinks
from superhero_project.domain.links import sync_metadata_edges
from superhero_project.domain.links import sync_wikilink_edges
from superhero_project.domain.location import LocationMetadata
from superhero_project.domain.lore import LoreMetadata
from superhero_project.domain.org import OrgMetadata
from superhero_project.domain.profile import ProfileMetadata
from superhero_project.domain.tech import TechMetadata
from superhero_project.routers._utils import fetch_article

_md = MarkdownIt().disable("html_block").disable("html_inline")

router = APIRouter(prefix="/articles", tags=["articles"])

_METADATA_SCHEMAS: dict[ArticleType, type[BaseModel]] = {
    ArticleType.profile: ProfileMetadata,
    ArticleType.event: EventMetadata,
    ArticleType.org: OrgMetadata,
    ArticleType.location: LocationMetadata,
    ArticleType.tech: TechMetadata,
    ArticleType.lore: LoreMetadata,
    ArticleType.comic: ComicMetadata,
    ArticleType.disambiguation: DisambiguationMetadata,
}


class ArticleCreate(BaseModel):
    """Request body for article creation."""

    article_type: ArticleType
    page_name: str
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
    page_name: str
    article_type: ArticleType
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


def _render(text: str, index: AliasIndex, page_name_map: PageNameMap) -> str:
    """Render a Markdown string to HTML, with wikilinks resolved to HTML anchors."""
    return str(_md.render(render_wikilinks(text, index, page_name_map)))


def _validate_metadata(
    article_type: ArticleType, data: dict[str, Any]
) -> dict[str, Any]:
    """Dispatch to the per-type Pydantic schema and raise 422 on failure."""
    try:
        return _METADATA_SCHEMAS[article_type](**data).model_dump()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _can_edit(user: User, article: Article) -> bool:
    """True if the user authored the article or holds an elevated role."""
    return user.id == article.author_id or user.role in (
        UserRole.moderator,
        UserRole.admin,
    )


def _to_out(
    article: Article, index: AliasIndex, page_name_map: PageNameMap
) -> ArticleOut:
    """Map an ORM Article (tags eagerly loaded) to ArticleOut; renders wikilinks."""
    return ArticleOut(
        id=article.id,
        page_name=article.page_name,
        article_type=article.article_type,
        schema_version=article.schema_version,
        metadata=article.metadata_,
        content=article.content,
        rendered_body=_render(article.content, index, page_name_map),
        author_id=article.author_id,
        status=article.status,
        created_at=article.created_at,
        updated_at=article.updated_at,
        published_at=article.published_at,
        tags=[t.tag for t in article.tags],
    )


class HistoryEntryOut(BaseModel):
    """Single history entry with a unified diff of content changes."""

    id: int
    editor_id: int
    editor_name: str
    edited_at: datetime
    content_diff: str


def _content_diff(before: str, after: str) -> str:
    """Return a unified diff string between two content snapshots."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(before_lines, after_lines))


async def _load_history(article: Article, db: AsyncSession) -> list[ArticleHistory]:
    """Fetch all history records for an article, ordered oldest first."""
    return list(
        (
            await db.execute(
                select(ArticleHistory)
                .where(ArticleHistory.article_id == article.id)
                .options(selectinload(ArticleHistory.editor))
                .order_by(ArticleHistory.edited_at.asc())
            )
        )
        .scalars()
        .all()
    )


def _compute_diffs(
    records: list[ArticleHistory], current_content: str
) -> list[HistoryEntryOut]:
    """Build HistoryEntryOut list by diffing each snapshot against the next."""
    result = []
    for i, entry in enumerate(records):
        after = (
            records[i + 1].content_snapshot if i + 1 < len(records) else current_content
        )
        result.append(
            HistoryEntryOut(
                id=entry.id,
                editor_id=entry.editor_id,
                editor_name=entry.editor.display_name,
                edited_at=entry.edited_at,
                content_diff=_content_diff(entry.content_snapshot, after),
            )
        )
    return result


async def _sync_edges(
    article_id: int,
    article_type: ArticleType,
    content: str,
    metadata: dict[str, Any],
    db: AsyncSession,
) -> tuple[AliasIndex, PageNameMap]:
    """Build link maps and sync wikilink + metadata edges for one article."""
    index, page_name_map = await build_link_maps(db)
    await sync_wikilink_edges(article_id, content, index, db)
    await sync_metadata_edges(article_id, article_type, metadata, index, db)
    return index, page_name_map


async def _build_response(
    article_id: int, index: AliasIndex, page_name_map: PageNameMap, db: AsyncSession
) -> ArticleOut:
    """Re-fetch an article with tags loaded and render it to ArticleOut."""
    result = await db.execute(
        select(Article)
        .where(Article.id == article_id)
        .options(selectinload(Article.tags))
    )
    return _to_out(result.scalar_one(), index, page_name_map)


class RenderRequest(BaseModel):
    """Request body for the Markdown render helper."""

    content: str


@router.post("/render", response_class=HTMLResponse)
async def render_markdown(body: RenderRequest, db: DB) -> Response:
    """Render a Markdown string to HTML — used by the live editor preview."""
    index, page_name_map = await build_link_maps(db)
    return HTMLResponse(_render(body.content, index, page_name_map))


@router.post("/", status_code=201)
async def create_article(request: Request, body: ArticleCreate, db: DB) -> ArticleOut:
    """Create a new article as a draft."""
    user = await get_current_user(request, db)
    if body.article_type == ArticleType.disambiguation:
        raise HTTPException(
            status_code=403,
            detail=(
                "Use POST /moderation/disambiguation to create disambiguation articles"
            ),
        )
    validated_meta = _validate_metadata(body.article_type, body.metadata)
    article = Article(
        page_name=body.page_name,
        article_type=body.article_type,
        metadata_=validated_meta,
        content=body.content,
        author_id=user.id,
        status=ArticleStatus.draft,
    )
    db.add(article)
    await db.flush()
    for tag in body.tags:
        db.add(ArticleTag(article_id=article.id, tag=tag))
    await db.commit()
    index, page_name_map = await _sync_edges(
        article.id, article.article_type, article.content, article.metadata_, db
    )
    await db.commit()
    return await _build_response(article.id, index, page_name_map, db)


@router.get("/{identifier}")
async def get_article(identifier: str, db: DB) -> ArticleOut:
    """Fetch a single article by page_name."""
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])
    index, page_name_map = await build_link_maps(db)
    return _to_out(article, index, page_name_map)


@router.put("/{identifier}")
async def update_article(
    request: Request, identifier: str, body: ArticleUpdate, db: DB
) -> ArticleOut:
    """Update an article, snapshotting the prior state to ArticleHistory first."""
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])

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

    old_metadata = article.metadata_

    if body.metadata is not None:
        article.metadata_ = _validate_metadata(article.article_type, body.metadata)
    if body.content is not None:
        article.content = body.content
    if body.tags is not None:
        await db.execute(delete(ArticleTag).where(ArticleTag.article_id == article.id))
        db.expire(article, ["tags"])
        db.add_all([ArticleTag(article_id=article.id, tag=tag) for tag in body.tags])

    await db.commit()
    index, page_name_map = await _sync_edges(
        article.id, article.article_type, article.content, article.metadata_, db
    )
    if body.metadata is not None and article.status == ArticleStatus.published:
        await backfill_on_alias_change(
            article.id, old_metadata, article.metadata_, article.article_type, db
        )
    await db.commit()
    return await _build_response(article.id, index, page_name_map, db)


@router.get("/{identifier}/history")
async def get_article_history(identifier: str, db: DB) -> list[HistoryEntryOut]:
    """Return the edit history for an article, oldest first, each with a content
    diff."""
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])
    return _compute_diffs(await _load_history(article, db), article.content)


@router.delete("/{identifier}", status_code=204)
async def delete_article(request: Request, identifier: str, db: DB) -> None:
    """Delete an article.

    Only the author or a moderator/admin may do this.
    """
    user = await get_current_user(request, db)
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])

    if not _can_edit(user, article):
        raise HTTPException(status_code=403, detail="Forbidden")

    await db.delete(article)
    await db.commit()
