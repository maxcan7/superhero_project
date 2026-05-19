"""FastAPI application factory."""

from pathlib import Path

from fastapi import Depends
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from superhero_project.config import settings
from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.dependencies import get_current_user_opt
from superhero_project.dependencies import get_db
from superhero_project.routers import articles
from superhero_project.routers import articles_html
from superhero_project.routers import auth
from superhero_project.routers import comments
from superhero_project.routers import community
from superhero_project.routers import moderation
from superhero_project.routers import votes
from superhero_project.routers._utils import ArticleListItem
from superhero_project.routers._utils import article_list_item

_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


async def _recent_articles(db: AsyncSession) -> list[ArticleListItem]:
    """Return the 20 most recently updated published articles as template dicts."""
    result = await db.execute(
        select(Article)
        .where(Article.status == ArticleStatus.published)
        .where(Article.article_type != ArticleType.disambiguation)
        .options(selectinload(Article.tags))
        .order_by(Article.updated_at.desc())
        .limit(20)
    )
    return [article_list_item(a) for a in result.scalars()]


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(title="Superhero Project")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )
    app.include_router(auth.router)
    app.include_router(articles_html.router)
    app.include_router(articles.router)
    app.include_router(moderation.router)
    app.include_router(votes.router)
    app.include_router(comments.router)
    app.include_router(community.tags_router)
    app.include_router(community.contributors_router)
    app.include_router(community.me_router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
        """Render the front page with the 20 most recently updated published
        articles."""
        return _templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "articles": await _recent_articles(db),
                "user": await get_current_user_opt(request, db),
            },
        )

    return app


app = create_app()
