"""Articles HTML view router — template-rendered endpoints."""

from itertools import groupby as _groupby
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy import ColumnElement
from sqlalchemy import Select
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project._templates import templates as _templates
from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import ArticleType
from superhero_project.db.models import Comment
from superhero_project.db.models import User
from superhero_project.db.models import Vote
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.dependencies import get_current_user_opt
from superhero_project.domain.infobox import build_infobox_links
from superhero_project.domain.links import build_link_maps
from superhero_project.domain.links import fetch_incoming_links
from superhero_project.domain.links import fetch_location_activity
from superhero_project.domain.links import fetch_org_members
from superhero_project.domain.links import fetch_outgoing_links
from superhero_project.routers._utils import fetch_article
from superhero_project.routers.articles import _can_edit
from superhero_project.routers.articles import _check_article_access
from superhero_project.routers.articles import _compute_diffs
from superhero_project.routers.articles import _load_history
from superhero_project.routers.articles import _to_out

router = APIRouter(prefix="/articles", tags=["articles"])

_CREATABLE_ARTICLE_TYPES = [t for t in ArticleType if t.creatable]


def _group_outgoing_links(
    links: list[dict[str, str | None]],
) -> list[tuple[str, list[dict[str, str | None]]]]:
    """Group outgoing links by field_name into labelled (label, entries) pairs."""
    result = []
    for field_name, entries in _groupby(links, key=lambda x: x["field_name"]):
        if field_name is None:
            label = "Mentioned in body"
        else:
            label = f"Via: {field_name.replace('_', ' ').title()}"
        result.append((label, list(entries)))
    return result


async def _load_vote_context(
    article_id: int, user: User | None, db: AsyncSession
) -> tuple[int, int, int, int | None]:
    """Return (upvotes, downvotes, score, user_vote) for an article."""
    all_votes = (
        (await db.execute(select(Vote).where(Vote.article_id == article_id)))
        .scalars()
        .all()
    )
    upvotes = sum(1 for v in all_votes if v.value > 0)
    downvotes = sum(1 for v in all_votes if v.value < 0)
    user_vote: int | None = None
    if user is not None:
        uv = (
            await db.execute(
                select(Vote).where(
                    Vote.article_id == article_id, Vote.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        user_vote = uv.value if uv else None
    return upvotes, downvotes, upvotes - downvotes, user_vote


async def _load_comments(article_id: int, db: AsyncSession) -> list[dict[str, object]]:
    """Return comment dicts for an article, oldest first."""
    rows = (
        (
            await db.execute(
                select(Comment)
                .where(Comment.article_id == article_id)
                .options(selectinload(Comment.author))
                .order_by(Comment.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": c.id,
            "author_id": c.author_id,
            "author_name": c.author.display_name,
            "body": c.body,
            "created_at": c.created_at,
        }
        for c in rows
    ]


@router.get("/new", response_class=HTMLResponse)
async def new_article_form(request: Request, db: DB) -> Response:
    """Render the article creation editor."""
    user = await get_current_user(request, db)
    return _templates.TemplateResponse(
        request=request,
        name="editor.html",
        context={
            "user": user,
            "article": None,
            "identifier": None,
            "article_types": _CREATABLE_ARTICLE_TYPES,
            "article_type_label": None,
        },
    )


_FILTER_CTX_DEFAULTS: dict[str, str | None] = {
    "type_filter": None,
    "status": None,
    "powers": None,
    "location_type": None,
    "org_type": None,
}


@router.get("/search", response_class=HTMLResponse)
async def search_form(request: Request, db: DB) -> Response:
    """Render the search form."""
    user = await get_current_user_opt(request, db)
    return _templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"user": user, "results": None, "q": None, **_FILTER_CTX_DEFAULTS},
    )


def _jsonb_contains(key: str, val: object) -> ColumnElement[bool]:
    """Return a JSONB containment condition for a single metadata key/value."""
    return Article.metadata_.op("@>")(type_coerce({key: val}, JSONB()))


def _type_condition(type_filter: str) -> ColumnElement[bool] | None:
    """Return an article_type equality condition, or None if type_filter is invalid."""
    try:
        return Article.article_type == ArticleType(type_filter.lower())
    except ValueError:
        return None


def _fts_condition(q: str) -> tuple[ColumnElement[bool], ColumnElement[Any]]:
    """Return (match condition, rank order-by) for a full-text query."""
    tsquery = func.plainto_tsquery("english", q)
    return (
        Article.search_vector.op("@@")(tsquery),
        func.ts_rank(Article.search_vector, tsquery).desc(),
    )


def _metadata_conditions(
    status: str | None,
    powers: str | None,
    location_type: str | None,
    org_type: str | None,
) -> list[ColumnElement[bool]]:
    """Return JSONB containment conditions for all active metadata filters."""
    conditions: list[ColumnElement[bool]] = []
    for val, key in [
        (status, "status"),
        (location_type, "location_type"),
        (org_type, "org_type"),
    ]:
        if val:
            conditions.append(_jsonb_contains(key, val.lower()))
    if powers:
        conditions.append(_jsonb_contains("powers", [powers.lower()]))
    return conditions


def _build_search_stmt(
    q: str | None,
    type_filter: str | None,
    status: str | None,
    powers: str | None,
    location_type: str | None,
    org_type: str | None,
) -> Select[tuple[Article]]:
    """Assemble a SELECT statement from the active query and filter params."""
    conditions: list[ColumnElement[bool]] = [Article.status == ArticleStatus.published]

    if type_filter is not None:
        if (cond := _type_condition(type_filter)) is not None:
            conditions.append(cond)

    order_by: ColumnElement[Any] = Article.page_name.asc()
    if q is not None:
        fts_cond, order_by = _fts_condition(q)
        safe_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        tag_cond = Article.id.in_(
            select(ArticleTag.article_id).where(ArticleTag.tag.ilike(f"%{safe_q}%"))
        )
        conditions.append(or_(fts_cond, tag_cond))

    conditions.extend(_metadata_conditions(status, powers, location_type, org_type))

    return (
        select(Article)
        .where(*conditions)
        .order_by(order_by)
        .options(selectinload(Article.tags))
    )


@router.get("/search/results", response_class=HTMLResponse)
async def search_articles(
    request: Request,
    db: DB,
    q: str | None = None,
    type_filter: str | None = Query(default=None, alias="type"),
    status: str | None = None,
    powers: str | None = None,
    location_type: str | None = None,
    org_type: str | None = None,
) -> Response:
    """Search published articles by full-text query and/or metadata filters."""
    user = await get_current_user_opt(request, db)
    filter_ctx = {
        "q": q,
        "type_filter": type_filter,
        "status": status,
        "powers": powers,
        "location_type": location_type,
        "org_type": org_type,
    }
    if all(v is None for v in filter_ctx.values()):
        return _templates.TemplateResponse(
            request=request,
            name="search.html",
            context={"user": user, "results": None, **filter_ctx},
        )

    stmt = _build_search_stmt(q, type_filter, status, powers, location_type, org_type)
    index, page_name_map = await build_link_maps(db)
    articles = (await db.execute(stmt)).scalars().all()
    results = [_to_out(a, index, page_name_map) for a in articles]
    return _templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"results": results, "user": user, **filter_ctx},
    )


@router.get("/{identifier}/view", response_class=HTMLResponse)
async def view_article_html(request: Request, identifier: str, db: DB) -> Response:
    """Render an article as an HTML page."""
    user = await get_current_user_opt(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    _check_article_access(user, article_db)
    index, page_name_map = await build_link_maps(db)
    article = _to_out(article_db, index, page_name_map)
    vote_upvotes, vote_downvotes, vote_score, user_vote = await _load_vote_context(
        article_db.id, user, db
    )
    outgoing = await fetch_outgoing_links(article_db.id, db)
    incoming = await fetch_incoming_links(article_db.id, db)
    return _templates.TemplateResponse(
        request=request,
        name="article.html",
        context={
            "article": article,
            "user": user,
            "can_edit": user is not None and _can_edit(user, article_db),
            "is_author": user is not None and user.id == article_db.author_id,
            "vote_upvotes": vote_upvotes,
            "vote_downvotes": vote_downvotes,
            "vote_score": vote_score,
            "user_vote": user_vote,
            "comments": await _load_comments(article_db.id, db),
            "outgoing_links": _group_outgoing_links(outgoing),
            "incoming_links": incoming,
            "infobox_links": build_infobox_links(
                outgoing, article_db.article_type, article_db.metadata_
            ),
        },
    )


@router.get("/{identifier}/members", response_class=HTMLResponse)
async def view_org_members(request: Request, identifier: str, db: DB) -> Response:
    """Render the org member roster derived from affiliation edges."""
    user = await get_current_user_opt(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    members = await fetch_org_members(article_db.id, db)
    grouped = [
        (status, list(entries))
        for status, entries in _groupby(members, key=lambda m: m["status"])
    ]
    index, page_name_map = await build_link_maps(db)
    article = _to_out(article_db, index, page_name_map)
    return _templates.TemplateResponse(
        request=request,
        name="members.html",
        context={"article": article, "user": user, "grouped_members": grouped},
    )


@router.get("/{identifier}/activity", response_class=HTMLResponse)
async def view_location_activity(request: Request, identifier: str, db: DB) -> Response:
    """Render the location activity derived view."""
    user = await get_current_user_opt(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    events, residents = await fetch_location_activity(article_db.id, db)
    index, page_name_map = await build_link_maps(db)
    article = _to_out(article_db, index, page_name_map)
    return _templates.TemplateResponse(
        request=request,
        name="activity.html",
        context={
            "article": article,
            "user": user,
            "events": events,
            "residents": residents,
        },
    )


@router.get("/{identifier}/history/view", response_class=HTMLResponse)
async def view_article_history(request: Request, identifier: str, db: DB) -> Response:
    """Render the edit history page with unified diffs for each revision."""
    user = await get_current_user_opt(request, db)
    article = await fetch_article(identifier, db, [selectinload(Article.tags)])
    index, page_name_map = await build_link_maps(db)
    return _templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "article": _to_out(article, index, page_name_map),
            "history": _compute_diffs(
                await _load_history(article, db), article.content
            ),
            "user": user,
        },
    )


@router.get("/{identifier}/edit", response_class=HTMLResponse)
async def edit_article_form(request: Request, identifier: str, db: DB) -> Response:
    """Render the article editor pre-populated with existing data."""
    user = await get_current_user(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    if not _can_edit(user, article_db):
        raise HTTPException(status_code=403, detail="Forbidden")
    index, page_name_map = await build_link_maps(db)
    article = _to_out(article_db, index, page_name_map)
    return _templates.TemplateResponse(
        request=request,
        name="editor.html",
        context={
            "user": user,
            "article": article,
            "identifier": article.page_name,
            "article_types": _CREATABLE_ARTICLE_TYPES,
            "article_type_label": article_db.article_type.label,
            "moderator_note": article_db.moderator_note,
        },
    )
