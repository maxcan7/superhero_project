"""Tests for the alias index, wikilink renderer, and wikilink parser in links.py."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.domain.links import AliasIndex
from superhero_project.domain.links import SlugMap
from superhero_project.domain.links import _extract_metadata_edges
from superhero_project.domain.links import build_alias_index
from superhero_project.domain.links import render_wikilinks
from superhero_project.domain.links import sync_metadata_edges
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


# --- _extract_metadata_edges (pure unit tests, no DB) ---

_EVENT_META: dict = {
    "event_date": None,
    "location": None,
    "participants": [],
    "outcome": None,
}
_LOCATION_META: dict = {
    "location_type": "city",
    "region": None,
    "status": "unknown",
    "notable_residents": [],
}
_TECH_META: dict = {
    "tech_type": "gear",
    "origin": None,
    "current_holder": None,
    "status": "unknown",
}
_LORE_META: dict = {"category": "other", "related_articles": []}
_COMIC_META: dict = {
    "comic_type": "series",
    "publishers": [],
    "first_issue": None,
    "last_issue": None,
    "status": "unknown",
}


@pytest.mark.parametrize(
    ("article_type", "metadata", "index", "expected"),
    [
        pytest.param(
            ArticleType.profile,
            {**_PROFILE_META, "affiliation": ["target"]},
            {"target": 99},
            [(99, "affiliation", "target")],
            id="profile-affiliation-list",
        ),
        pytest.param(
            ArticleType.profile,
            {**_PROFILE_META, "base_of_operations": "target"},
            {"target": 99},
            [(99, "base_of_operations", "target")],
            id="profile-base-scalar",
        ),
        pytest.param(
            ArticleType.event,
            {**_EVENT_META, "location": "target"},
            {"target": 99},
            [(99, "location", "target")],
            id="event-location-scalar",
        ),
        pytest.param(
            ArticleType.event,
            {**_EVENT_META, "participants": ["target"]},
            {"target": 99},
            [(99, "participants", "target")],
            id="event-participants-list",
        ),
        pytest.param(
            ArticleType.org,
            {**_ORG_META, "headquarters": "target"},
            {"target": 99},
            [(99, "headquarters", "target")],
            id="org-headquarters-scalar",
        ),
        pytest.param(
            ArticleType.org,
            {**_ORG_META, "affiliation": ["target"]},
            {"target": 99},
            [(99, "affiliation", "target")],
            id="org-affiliation-list",
        ),
        pytest.param(
            ArticleType.location,
            {**_LOCATION_META, "notable_residents": ["target"]},
            {"target": 99},
            [(99, "notable_residents", "target")],
            id="location-residents-list",
        ),
        pytest.param(
            ArticleType.tech,
            {**_TECH_META, "current_holder": "target"},
            {"target": 99},
            [(99, "current_holder", "target")],
            id="tech-holder-scalar",
        ),
        pytest.param(
            ArticleType.lore,
            {**_LORE_META, "related_articles": ["target"]},
            {"target": 99},
            [(99, "related_articles", "target")],
            id="lore-related-list",
        ),
        pytest.param(
            ArticleType.comic,
            {**_COMIC_META, "publishers": ["target"]},
            {"target": 99},
            [(99, "publishers", "target")],
            id="comic-publishers-list",
        ),
        pytest.param(
            ArticleType.profile,
            {**_PROFILE_META, "affiliation": ["nobody"]},
            {},
            [],
            id="drops-unresolved",
        ),
        pytest.param(
            ArticleType.profile,
            {**_PROFILE_META, "affiliation": ["target", "alias"]},
            {"target": 99, "alias": 99},
            [(99, "affiliation", "alias")],
            id="deduplicates",
        ),
        pytest.param(
            ArticleType.disambiguation,
            {},
            {"anything": 1},
            [],
            id="no-handler",
        ),
    ],
)
def test_extract_metadata_edges(
    article_type: ArticleType,
    metadata: dict[str, str | list[str] | None],
    index: AliasIndex,
    expected: list[tuple[int, str, str]],
) -> None:
    """Resolves per-type metadata fields to (target_id, field_name, resolved_via)."""
    assert _extract_metadata_edges(article_type, metadata, index) == expected


# --- sync_metadata_edges (integration tests with DB) ---


async def _get_metadata_edges(db: AsyncSession, source_id: int) -> list[dict]:
    """Return all metadata edges (field_name NOT NULL) for source_id as plain dicts."""
    rows = await db.execute(
        text(
            "SELECT target_id, field_name, resolved_via FROM article_links"
            " WHERE source_id = :source_id AND field_name IS NOT NULL"
            " ORDER BY field_name, target_id"
        ),
        {"source_id": source_id},
    )
    return [dict(r._mapping) for r in rows]


@pytest.fixture
async def metadata_edge_pair(db: AsyncSession, user: User) -> tuple:
    """A (target, source, index) triple for metadata edge integration tests."""
    target = await make_article(
        db,
        user,
        slug="gotham",
        article_type=ArticleType.location,
        metadata_=_LOCATION_META,
    )
    source = await make_article(
        db,
        user,
        slug="batman",
        article_type=ArticleType.profile,
        metadata_=_PROFILE_META,
    )
    return target, source, {"gotham": target.id}


async def test_sync_metadata_edges_writes_to_db(
    db: AsyncSession, metadata_edge_pair: tuple
) -> None:
    """Resolved metadata edges are persisted to article_links."""
    target, source, index = metadata_edge_pair
    await sync_metadata_edges(
        source.id,
        ArticleType.profile,
        {**_PROFILE_META, "base_of_operations": "gotham"},
        index,
        db,
    )
    await db.commit()
    assert await _get_metadata_edges(db, source.id) == [
        {
            "target_id": target.id,
            "field_name": "base_of_operations",
            "resolved_via": "gotham",
        }
    ]


async def test_sync_metadata_edges_replaces_on_resave(
    db: AsyncSession, metadata_edge_pair: tuple
) -> None:
    """Re-syncing clears stale metadata edges before writing fresh ones."""
    _, source, index = metadata_edge_pair
    await sync_metadata_edges(
        source.id,
        ArticleType.profile,
        {**_PROFILE_META, "base_of_operations": "gotham"},
        index,
        db,
    )
    await db.commit()
    await sync_metadata_edges(source.id, ArticleType.profile, _PROFILE_META, index, db)
    await db.commit()
    assert await _get_metadata_edges(db, source.id) == []
