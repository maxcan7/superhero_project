"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from superhero_project.config import settings
from superhero_project.routers import articles
from superhero_project.routers import auth


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(title="Superhero Project")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.include_router(auth.router)
    app.include_router(articles.router)
    return app


app = create_app()
