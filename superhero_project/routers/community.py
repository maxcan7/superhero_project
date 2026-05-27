"""Community router: tag browsing, contributor profiles, and personal pages."""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.responses import Response

from superhero_project._templates import templates as _templates
from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import ArticleType
from superhero_project.db.models import Notification
from superhero_project.db.models import User
from superhero_project.dependencies import DB
from superhero_project.dependencies import get_current_user
from superhero_project.dependencies import get_current_user_opt
from superhero_project.routers._utils import article_list_item

tags_router = APIRouter(prefix="/tags", tags=["tags"])
contributors_router = APIRouter(prefix="/contributors", tags=["contributors"])
me_router = APIRouter(prefix="/me", tags=["me"])


# ── Tag browsing ───────────────────────────────────────────────────────────────


@tags_router.get("", response_class=HTMLResponse)
async def tag_index(request: Request, db: DB) -> Response:
    """Render the tag index with article counts for each tag."""
    user = await get_current_user_opt(request, db)
    rows = (
        await db.execute(
            select(ArticleTag.tag, func.count(ArticleTag.article_id).label("count"))
            .join(Article, ArticleTag.article_id == Article.id)
            .where(Article.status == ArticleStatus.published)
            .group_by(ArticleTag.tag)
            .order_by(ArticleTag.tag)
        )
    ).all()
    return _templates.TemplateResponse(
        request=request,
        name="tags/index.html",
        context={
            "tags": [{"tag": r.tag, "count": r.count} for r in rows],
            "user": user,
        },
    )


@tags_router.get("/{tag}", response_class=HTMLResponse)
async def tag_detail(request: Request, tag: str, db: DB) -> Response:
    """Render the list of published articles carrying a given tag."""
    user = await get_current_user_opt(request, db)
    articles = (
        (
            await db.execute(
                select(Article)
                .join(ArticleTag, Article.id == ArticleTag.article_id)
                .where(ArticleTag.tag == tag, Article.status == ArticleStatus.published)
                .where(Article.article_type != ArticleType.disambiguation)
                .options(selectinload(Article.tags))
                .order_by(Article.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return _templates.TemplateResponse(
        request=request,
        name="tags/detail.html",
        context={
            "tag": tag,
            "articles": [article_list_item(a) for a in articles],
            "user": user,
        },
    )


# ── Contributor profiles ───────────────────────────────────────────────────────


@contributors_router.get("/{username}", response_class=HTMLResponse)
async def contributor_profile(request: Request, username: str, db: DB) -> Response:
    """Render a contributor's profile listing their published articles."""
    user = await get_current_user_opt(request, db)
    profile_user = (
        await db.execute(select(User).where(User.github_username == username))
    ).scalar_one_or_none()
    if profile_user is None:
        raise HTTPException(status_code=404, detail="Contributor not found")
    articles = (
        (
            await db.execute(
                select(Article)
                .where(
                    Article.author_id == profile_user.id,
                    Article.status == ArticleStatus.published,
                )
                .where(Article.article_type != ArticleType.disambiguation)
                .options(selectinload(Article.tags))
                .order_by(Article.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return _templates.TemplateResponse(
        request=request,
        name="contributors/profile.html",
        context={
            "profile_user": profile_user,
            "articles": [article_list_item(a) for a in articles],
            "user": user,
        },
    )


# ── Personal pages ─────────────────────────────────────────────────────────────


@me_router.get("/notifications", response_class=HTMLResponse)
async def my_notifications(request: Request, db: DB) -> Response:
    """Render the current user's notification inbox, marking all as read."""
    user = await get_current_user(request, db)
    notifications = (
        (
            await db.execute(
                select(Notification)
                .where(Notification.user_id == user.id)
                .order_by(Notification.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for n in notifications:
        n.read = True
    await db.commit()
    return _templates.TemplateResponse(
        request=request,
        name="me/notifications.html",
        context={"notifications": notifications, "user": user},
    )


@me_router.get("/articles", response_class=HTMLResponse)
async def my_articles(request: Request, db: DB) -> Response:
    """Render the current user's articles across all statuses."""
    user = await get_current_user(request, db)
    articles = (
        (
            await db.execute(
                select(Article)
                .where(Article.author_id == user.id)
                .options(selectinload(Article.tags))
                .order_by(Article.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return _templates.TemplateResponse(
        request=request,
        name="me/articles.html",
        context={
            "articles": [article_list_item(a) for a in articles],
            "user": user,
        },
    )
