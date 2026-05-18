"""Tests for the alias index in superhero_project.domain.links."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.domain.links import build_alias_index
from tests.utils import make_article

pytestmark = pytest.mark.anyio

_ORG_META: dict = {
    "aliases": [],
    "org_type": "team",
    "founded": None,
    "headquarters": None,
    "status": "active",
    "affiliation": [],
}
_PROFILE_META: dict = {
    "aliases": [],
    "affiliation": [],
    "powers": [],
    "status": "active",
    "base_of_operations": None,
    "first_appearance": None,
}


@pytest.mark.parametrize(
    ("slug", "article_type", "designation", "metadata_", "expected_keys"),
    [
        pytest.param(
            "S.H.I.E.L.D",
            ArticleType.org,
            None,
            {**_ORG_META, "aliases": ["Shield"]},
            ["s.h.i.e.l.d", "shield"],
            id="org-slug-normalized-and-aliases",
        ),
        pytest.param(
            "iron-man",
            ArticleType.profile,
            "CAPE-0042",
            {**_PROFILE_META, "aliases": ["Iron Man", "Tony Stark"]},
            ["iron-man", "cape-0042", "iron man", "tony stark"],
            id="profile-slug-designation-aliases",
        ),
    ],
)
async def test_aliases_indexed(
    db: AsyncSession,
    user: User,
    slug: str,
    article_type: ArticleType,
    designation: str | None,
    metadata_: dict,
    expected_keys: list[str],
) -> None:
    """Published article aliases (slug, designation, metadata) are all indexed."""
    a = await make_article(
        db,
        user,
        slug=slug,
        article_type=article_type,
        designation=designation,
        metadata_=metadata_,
    )
    index = await build_alias_index(db)
    for key in expected_keys:
        assert index[key] == a.id


@pytest.mark.parametrize("status", [ArticleStatus.draft, ArticleStatus.pending])
async def test_unpublished_excluded(
    db: AsyncSession, user: User, status: ArticleStatus
) -> None:
    """Draft and pending articles are excluded from the alias index."""
    await make_article(
        db,
        user,
        slug="secret",
        article_type=ArticleType.profile,
        metadata_=_PROFILE_META,
        status=status,
    )
    assert "secret" not in await build_alias_index(db)


async def test_disambiguation_slug_excluded(db: AsyncSession, user: User) -> None:
    """Disambiguation slugs are not indexed as direct resolutions."""
    await make_article(
        db, user, slug="mercury", article_type=ArticleType.disambiguation, metadata_={}
    )
    assert "mercury" not in await build_alias_index(db)
