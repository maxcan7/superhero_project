"""Tests for the alias index, wikilink renderer, and wikilink parser in links.py."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.domain.links import AliasIndex
from superhero_project.domain.links import SlugMap
from superhero_project.domain.links import build_alias_index
from superhero_project.domain.links import render_wikilinks
from superhero_project.domain.links import sync_wikilink_edges
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


# --- render_wikilinks (pure unit tests, no DB) ---


@pytest.mark.parametrize(
    ("content", "index", "slug_map", "expected"),
    [
        pytest.param(
            "See [[Iron Man]].",
            {"iron man": 1},
            {1: "iron-man"},
            'See <a href="/articles/iron-man">Iron Man</a>.',
            id="resolved",
        ),
        pytest.param(
            "[[Iron Man|Tony]]",
            {"iron man": 1},
            {1: "iron-man"},
            '<a href="/articles/iron-man">Tony</a>',
            id="resolved-display-text",
        ),
        pytest.param(
            "[[Unknown Hero]]",
            {},
            {},
            '<a href="/articles/new?slug=unknown hero" class="red-link">'
            "Unknown Hero</a>",
            id="unresolved-red-link",
        ),
        pytest.param(
            "[[Avengers]] and [[Ghost]].",
            {"avengers": 1},
            {1: "avengers"},
            '<a href="/articles/avengers">Avengers</a>'
            ' and <a href="/articles/new?slug=ghost" class="red-link">Ghost</a>.',
            id="mixed-resolved-and-unresolved",
        ),
    ],
)
def test_render_wikilinks(
    content: str, index: AliasIndex, slug_map: SlugMap, expected: str
) -> None:
    """Wikilinks render as HTML anchors; unresolved targets become red-links."""
    assert render_wikilinks(content, index, slug_map) == expected


# --- sync_wikilink_edges (integration tests with DB) ---


async def _get_wikilink_edges(db: AsyncSession, source_id: int) -> list[dict]:
    """Return all wikilink edges (field_name NULL) for source_id as plain dicts."""
    rows = await db.execute(
        text(
            "SELECT target_id, field_name, resolved_via FROM article_links"
            " WHERE source_id = :source_id ORDER BY target_id"
        ),
        {"source_id": source_id},
    )
    return [dict(r._mapping) for r in rows]


@pytest.mark.parametrize(
    ("content", "aliases", "expected_count"),
    [
        pytest.param("[[Avengers]]", ["avengers"], 1, id="creates-edge"),
        pytest.param("[[Unknown]]", [], 0, id="drops-unresolved"),
        pytest.param(
            "[[Avengers]] and [[Ally]]", ["avengers", "ally"], 1, id="deduplicates"
        ),
    ],
)
async def test_sync_wikilink_edges(
    db: AsyncSession,
    user: User,
    content: str,
    aliases: list[str],
    expected_count: int,
) -> None:
    """Wikilink edges are created, deduplicated, and dropped for unresolved targets."""
    target = await make_article(
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=_ORG_META
    )
    source = await make_article(
        db,
        user,
        slug="source",
        article_type=ArticleType.profile,
        metadata_=_PROFILE_META,
    )
    index: AliasIndex = {alias: target.id for alias in aliases}
    await sync_wikilink_edges(source.id, content, index, db)
    await db.commit()
    assert len(await _get_wikilink_edges(db, source.id)) == expected_count


async def test_sync_wikilink_edges_replaces_on_resave(
    db: AsyncSession, user: User
) -> None:
    """Re-syncing clears old wikilink edges before writing fresh ones."""
    target = await make_article(
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=_ORG_META
    )
    source = await make_article(
        db,
        user,
        slug="spider-man",
        article_type=ArticleType.profile,
        metadata_=_PROFILE_META,
    )
    index: AliasIndex = {"avengers": target.id}
    await sync_wikilink_edges(source.id, "[[Avengers]]", index, db)
    await db.commit()
    await sync_wikilink_edges(source.id, "no links here", index, db)
    await db.commit()
    assert await _get_wikilink_edges(db, source.id) == []
