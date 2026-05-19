"""Articles HTML view router — template-rendered endpoints."""

from itertools import groupby as _groupby
from pathlib import Path

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
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
from superhero_project.routers.articles import _compute_diffs
from superhero_project.routers.articles import _load_history
from superhero_project.routers.articles import _to_out

_templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

router = APIRouter(prefix="/articles", tags=["articles"])


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
        context={"user": user, "article": None, "identifier": None},
    )


@router.get("/search", response_class=HTMLResponse)
async def search_form(request: Request, db: DB) -> Response:
    """Render the search form."""
    user = await get_current_user_opt(request, db)
    return _templates.TemplateResponse(
        request=request, name="search.html", context={"user": user, "results": None}
    )


@router.get("/search/results", response_class=HTMLResponse)
async def search_articles(request: Request, db: DB, q: str) -> Response:
    """Full-text search over published articles, ranked by relevance."""
    tsquery = func.plainto_tsquery("english", q)
    stmt = (
        select(Article)
        .where(
            Article.status == ArticleStatus.published,
            Article.search_vector.op("@@")(tsquery),
        )
        .order_by(func.ts_rank(Article.search_vector, tsquery).desc())
        .options(selectinload(Article.tags))
    )
    index, slug_map = await build_link_maps(db)
    articles = (await db.execute(stmt)).scalars().all()
    results = [_to_out(a, index, slug_map) for a in articles]
    user = await get_current_user_opt(request, db)
    return _templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"q": q, "results": results, "user": user},
    )


@router.get("/{identifier}/view", response_class=HTMLResponse)
async def view_article_html(request: Request, identifier: str, db: DB) -> Response:
    """Render an article as an HTML page."""
    user = await get_current_user_opt(request, db)
    article_db = await fetch_article(identifier, db, [selectinload(Article.tags)])
    index, slug_map = await build_link_maps(db)
    article = _to_out(article_db, index, slug_map)
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
    index, slug_map = await build_link_maps(db)
    article = _to_out(article_db, index, slug_map)
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
    index, slug_map = await build_link_maps(db)
    article = _to_out(article_db, index, slug_map)
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
    index, slug_map = await build_link_maps(db)
    return _templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "article": _to_out(article, index, slug_map),
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
    index, slug_map = await build_link_maps(db)
    article = _to_out(article_db, index, slug_map)
    return _templates.TemplateResponse(
        request=request,
        name="editor.html",
        context={
            "user": user,
            "article": article,
            "identifier": article.designation or article.slug,
        },
    )
