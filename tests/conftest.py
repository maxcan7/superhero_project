"""Shared pytest fixtures."""

import getpass
from collections.abc import AsyncGenerator
from collections.abc import Generator
from datetime import datetime

import pytest
from httpx import ASGITransport
from httpx import AsyncClient
from pytest_postgresql import factories
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from superhero_project._limiter import limiter
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

pg_noproc = factories.postgresql_noproc(user=getpass.getuser())
pg = factories.postgresql("pg_noproc")


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None, None, None]:
    """Reset the rate limiter between tests."""
    # global singleton — revisit if pytest-xdist parallelism is added
    yield
    limiter.reset()


@pytest.fixture
async def engine(pg) -> AsyncGenerator[AsyncEngine, None]:
    """Postgres engine with schema created fresh per test."""
    info = pg.info
    url = f"postgresql+asyncpg://{info.user}@{info.host}:{info.port}/{info.dbname}"
    e = create_async_engine(url)
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

    def _override_get_db() -> Generator[AsyncSession, None, None]:
        """Yield the test DB session in place of the real dependency."""
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

    def _override_get_db() -> Generator[AsyncSession, None, None]:
        """Yield the test DB session in place of the real dependency."""
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

    def _override_get_db() -> Generator[AsyncSession, None, None]:
        """Yield the test DB session in place of the real dependency."""
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
async def moderator(db: AsyncSession) -> User:
    """A persisted moderator user."""
    u = User(
        github_id=3,
        github_username="moduser",
        display_name="Mod User",
        role=UserRole.moderator,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
async def mod_auth_client(
    db: AsyncSession, moderator: User
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with a valid session cookie for the moderator user."""
    app = create_app()

    def _override_get_db() -> Generator[AsyncSession, None, None]:
        """Yield the test DB session in place of the real dependency."""
        yield db

    app.dependency_overrides[get_db] = _override_get_db

    cookie = make_session_cookie(
        {"user_id": moderator.id, "role": moderator.role.value}, settings.session_secret
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": cookie},
    ) as ac:
        yield ac


@pytest.fixture
async def draft_article(db: AsyncSession, user: User) -> Article:
    """A draft profile article."""
    article = Article(
        page_name="draft-profile",
        article_type=ArticleType.profile,
        metadata_={
            "aliases": [],
            "affiliation": [],
            "powers": [],
            "status": "active",
            "base_of_operations": None,
            "first_appearance": None,
        },
        content="# Draft Hero",
        author_id=user.id,
        status=ArticleStatus.draft,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@pytest.fixture
async def pending_article(db: AsyncSession, user: User) -> Article:
    """A pending profile article awaiting moderation."""
    article = Article(
        page_name="pending-profile",
        article_type=ArticleType.profile,
        metadata_={
            "aliases": [],
            "affiliation": [],
            "powers": [],
            "status": "active",
            "base_of_operations": None,
            "first_appearance": None,
        },
        content="# Pending Hero",
        author_id=user.id,
        status=ArticleStatus.pending,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@pytest.fixture
async def published_article(db: AsyncSession, user: User) -> Article:
    """A published profile article with minimal valid metadata and one tag."""
    article = Article(
        page_name="the-guardian",
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


@pytest.fixture
async def edited_article(
    auth_client: AsyncClient, published_article: Article
) -> Article:
    """Published article that has been edited once, creating one history entry."""
    url = f"/articles/{published_article.page_name}"
    await auth_client.put(url, json={"content": "v2"})
    return published_article
