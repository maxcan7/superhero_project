"""Shared pytest fixtures."""

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
from httpx import ASGITransport
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from superhero_project.config import settings
from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleTag
from superhero_project.db.models import ArticleType
from superhero_project.db.models import Base
from superhero_project.db.models import User
from superhero_project.db.models import UserRole
from superhero_project.dependencies import get_db
from superhero_project.main import create_app
from tests.utils import make_session_cookie


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """In-memory SQLite engine with schema created fresh per test."""
    e = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with e.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    await e.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Single session tied to the in-memory engine."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to a fresh app instance with the DB dependency overridden."""
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def user(db: AsyncSession) -> User:
    """A persisted contributor user."""
    u = User(
        github_id=1,
        github_username="testuser",
        display_name="Test User",
        role=UserRole.contributor,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
async def other_user(db: AsyncSession) -> User:
    """A second contributor user, used to test forbidden access."""
    u = User(
        github_id=2,
        github_username="otheruser",
        display_name="Other User",
        role=UserRole.contributor,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
async def auth_client(
    db: AsyncSession, user: User
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with a valid session cookie for the primary test user."""
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    cookie = make_session_cookie(
        {"user_id": user.id, "role": user.role.value}, settings.session_secret
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": cookie},
    ) as ac:
        yield ac


@pytest.fixture
async def other_auth_client(
    db: AsyncSession, other_user: User
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with a valid session cookie for the second test user."""
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    cookie = make_session_cookie(
        {"user_id": other_user.id, "role": other_user.role.value},
        settings.session_secret,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": cookie},
    ) as ac:
        yield ac


@pytest.fixture
async def published_article(db: AsyncSession, user: User) -> Article:
    """A published profile article with minimal valid metadata and one tag."""
    article = Article(
        slug="CAPE-0001",
        designation="CAPE-0001",
        article_type=ArticleType.profile,
        metadata_={
            "aliases": ["The Guardian"],
            "affiliation": [],
            "powers": ["flight", "strength"],
            "status": "active",
            "base_of_operations": None,
            "first_appearance": None,
        },
        content="# The Guardian\n\nProtector of the city.",
        author_id=user.id,
        status=ArticleStatus.published,
        published_at=datetime(2025, 1, 1),
    )
    db.add(article)
    await db.flush()
    db.add(ArticleTag(article_id=article.id, tag="hero"))
    await db.commit()
    await db.refresh(article)
    return article
