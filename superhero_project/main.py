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
from superhero_project.db.models import User
from superhero_project.dependencies import get_db
from superhero_project.routers import articles
from superhero_project.routers import auth

_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(title="Superhero Project")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(auth.router)
    app.include_router(articles.router)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
        """Render the front page with the 20 most recently updated published
        articles."""
        result = await db.execute(
            select(Article)
            .where(Article.status == ArticleStatus.published)
            .options(selectinload(Article.tags))
            .order_by(Article.updated_at.desc())
            .limit(20)
        )
        article_rows = result.scalars().all()

        user: User | None = None
        user_id = request.session.get("user_id")
        if user_id:
            user = await db.get(User, user_id)

        article_list = [
            {
                "slug": a.slug,
                "designation": a.designation,
                "article_type": a.article_type,
                "metadata": a.metadata_,
                "tags": [t.tag for t in a.tags],
            }
            for a in article_rows
        ]
        return _templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"articles": article_list, "user": user},
        )

    return app


app = create_app()
