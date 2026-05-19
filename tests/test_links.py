"""Tests for the alias index, wikilink renderer, and wikilink parser in links.py."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.db.models import User
from superhero_project.domain.links import AliasIndex
from superhero_project.domain.links import SlugMap
from superhero_project.domain.links import _extract_metadata_edges
from superhero_project.domain.links import _find_articles_referencing
from superhero_project.domain.links import backfill_on_alias_change
from superhero_project.domain.links import backfill_on_publish
from superhero_project.domain.links import build_alias_index
from superhero_project.domain.links import fetch_incoming_links
from superhero_project.domain.links import fetch_org_members
from superhero_project.domain.links import fetch_outgoing_links
from superhero_project.domain.links import render_wikilinks
from superhero_project.domain.links import sync_metadata_edges
from superhero_project.domain.links import sync_wikilink_edges
from tests.utils import COMIC_META
from tests.utils import EVENT_META
from tests.utils import GOTHAM_EDGE
from tests.utils import LOCATION_META
from tests.utils import LORE_META
from tests.utils import ORG_META
from tests.utils import PROFILE_META
from tests.utils import TECH_META
from tests.utils import WIKILINK_EDGE
from tests.utils import make_article

pytestmark = pytest.mark.anyio


# --- build_alias_index ---


@pytest.mark.parametrize(
    ("slug", "article_type", "designation", "metadata_", "expected_keys"),
    [
        pytest.param(
            "S.H.I.E.L.D",
            ArticleType.org,
            None,
            {**ORG_META, "aliases": ["Shield"]},
            ["s.h.i.e.l.d", "shield"],
            id="org-slug-normalized-and-aliases",
        ),
        pytest.param(
            "iron-man",
            ArticleType.profile,
            "CAPE-0042",
            {**PROFILE_META, "aliases": ["Iron Man", "Tony Stark"]},
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
        metadata_=PROFILE_META,
        status=status,
    )
    assert "secret" not in await build_alias_index(db)


async def test_disambiguation_slug_in_index(db: AsyncSession, user: User) -> None:
    """Disambiguation slugs are indexed and resolve to the disambiguation article."""
    a = await make_article(
        db, user, slug="mercury", article_type=ArticleType.disambiguation, metadata_={}
    )
    assert await build_alias_index(db) == {"mercury": a.id}


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
        pytest.param(
            "[[Mercury]]",
            {"mercury": 5},
            {5: "mercury"},
            '<a href="/articles/mercury">Mercury</a>',
            id="disambiguation-page-link",
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
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=ORG_META
    )
    source = await make_article(
        db,
        user,
        slug="source",
        article_type=ArticleType.profile,
        metadata_=PROFILE_META,
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
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=ORG_META
    )
    source = await make_article(
        db,
        user,
        slug="spider-man",
        article_type=ArticleType.profile,
        metadata_=PROFILE_META,
    )
    index: AliasIndex = {"avengers": target.id}
    await sync_wikilink_edges(source.id, "[[Avengers]]", index, db)
    await db.commit()
    await sync_wikilink_edges(source.id, "no links here", index, db)
    await db.commit()
    assert await _get_wikilink_edges(db, source.id) == []


# --- _extract_metadata_edges (pure unit tests, no DB) ---


@pytest.mark.parametrize(
    ("article_type", "metadata", "index", "expected"),
    [
        pytest.param(
            ArticleType.profile,
            {**PROFILE_META, "affiliation": ["target"]},
            {"target": 99},
            [(99, "affiliation", "target")],
            id="profile-affiliation-list",
        ),
        pytest.param(
            ArticleType.profile,
            {**PROFILE_META, "base_of_operations": "target"},
            {"target": 99},
            [(99, "base_of_operations", "target")],
            id="profile-base-scalar",
        ),
        pytest.param(
            ArticleType.event,
            {**EVENT_META, "location": "target"},
            {"target": 99},
            [(99, "location", "target")],
            id="event-location-scalar",
        ),
        pytest.param(
            ArticleType.event,
            {**EVENT_META, "participants": ["target"]},
            {"target": 99},
            [(99, "participants", "target")],
            id="event-participants-list",
        ),
        pytest.param(
            ArticleType.org,
            {**ORG_META, "headquarters": "target"},
            {"target": 99},
            [(99, "headquarters", "target")],
            id="org-headquarters-scalar",
        ),
        pytest.param(
            ArticleType.org,
            {**ORG_META, "affiliation": ["target"]},
            {"target": 99},
            [(99, "affiliation", "target")],
            id="org-affiliation-list",
        ),
        pytest.param(
            ArticleType.location,
            {**LOCATION_META, "notable_residents": ["target"]},
            {"target": 99},
            [(99, "notable_residents", "target")],
            id="location-residents-list",
        ),
        pytest.param(
            ArticleType.tech,
            {**TECH_META, "current_holder": "target"},
            {"target": 99},
            [(99, "current_holder", "target")],
            id="tech-holder-scalar",
        ),
        pytest.param(
            ArticleType.lore,
            {**LORE_META, "related_articles": ["target"]},
            {"target": 99},
            [(99, "related_articles", "target")],
            id="lore-related-list",
        ),
        pytest.param(
            ArticleType.comic,
            {**COMIC_META, "publishers": ["target"]},
            {"target": 99},
            [(99, "publishers", "target")],
            id="comic-publishers-list",
        ),
        pytest.param(
            ArticleType.profile,
            {**PROFILE_META, "affiliation": ["nobody"]},
            {},
            [],
            id="drops-unresolved",
        ),
        pytest.param(
            ArticleType.profile,
            {**PROFILE_META, "affiliation": ["target", "alias"]},
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
        metadata_=LOCATION_META,
    )
    source = await make_article(
        db,
        user,
        slug="batman",
        article_type=ArticleType.profile,
        metadata_=PROFILE_META,
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
        {**PROFILE_META, "base_of_operations": "gotham"},
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
        {**PROFILE_META, "base_of_operations": "gotham"},
        index,
        db,
    )
    await db.commit()
    await sync_metadata_edges(source.id, ArticleType.profile, PROFILE_META, index, db)
    await db.commit()
    assert await _get_metadata_edges(db, source.id) == []


# --- fetch_outgoing_links / fetch_incoming_links (integration tests with DB) ---


@pytest.mark.parametrize(
    ("content", "meta_override", "expected"),
    [
        pytest.param("[[gotham]]", {}, [WIKILINK_EDGE], id="wikilink-edge"),
        pytest.param(
            "", {"base_of_operations": "gotham"}, [GOTHAM_EDGE], id="metadata-edge"
        ),
        pytest.param(
            "[[gotham]]",
            {"base_of_operations": "gotham"},
            [WIKILINK_EDGE, GOTHAM_EDGE],
            id="wikilink-and-metadata-edge",
        ),
    ],
)
async def test_fetch_outgoing_links(
    db: AsyncSession,
    user: User,
    content: str,
    meta_override: dict,
    expected: list[dict],
) -> None:
    """Outgoing wikilink and metadata edges appear in fetch_outgoing_links results."""
    target = await make_article(
        db,
        user,
        slug="gotham",
        article_type=ArticleType.location,
        metadata_=LOCATION_META,
    )
    source = await make_article(
        db,
        user,
        slug="batman",
        article_type=ArticleType.profile,
        metadata_={**PROFILE_META, **meta_override},
        content=content,
    )
    index: AliasIndex = {"gotham": target.id}
    await sync_wikilink_edges(source.id, content, index, db)
    await sync_metadata_edges(
        source.id, ArticleType.profile, {**PROFILE_META, **meta_override}, index, db
    )
    await db.commit()
    assert await fetch_outgoing_links(source.id, db) == expected


async def test_fetch_incoming_links(db: AsyncSession, user: User) -> None:
    """Incoming wikilink and metadata edges appear in fetch_incoming_links results."""
    target = await make_article(
        db,
        user,
        slug="gotham",
        article_type=ArticleType.location,
        metadata_=LOCATION_META,
    )
    source = await make_article(
        db,
        user,
        slug="batman",
        article_type=ArticleType.profile,
        metadata_={**PROFILE_META, "base_of_operations": "gotham"},
    )
    index: AliasIndex = {"gotham": target.id}
    await sync_wikilink_edges(source.id, "[[gotham]]", index, db)
    await sync_metadata_edges(
        source.id,
        ArticleType.profile,
        {**PROFILE_META, "base_of_operations": "gotham"},
        index,
        db,
    )
    await db.commit()
    rows = await fetch_incoming_links(target.id, db)
    assert rows == [
        {"slug": "batman", "article_type": "profile", "field_name": None},
        {
            "slug": "batman",
            "article_type": "profile",
            "field_name": "base_of_operations",
        },
    ]


@pytest.mark.parametrize(
    ("target_status", "source_status", "fetch_fn", "article_role"),
    [
        pytest.param(
            ArticleStatus.draft,
            ArticleStatus.published,
            fetch_outgoing_links,
            "source",
            id="outgoing-excludes-draft-target",
        ),
        pytest.param(
            ArticleStatus.published,
            ArticleStatus.draft,
            fetch_incoming_links,
            "target",
            id="incoming-excludes-draft-source",
        ),
    ],
)
async def test_fetch_links_excludes_unpublished(
    db: AsyncSession,
    user: User,
    target_status: ArticleStatus,
    source_status: ArticleStatus,
    fetch_fn,
    article_role: str,
) -> None:
    """Edges to/from unpublished articles are excluded from fetch results."""
    target = await make_article(
        db,
        user,
        slug="gotham",
        article_type=ArticleType.location,
        metadata_=LOCATION_META,
        status=target_status,
    )
    source = await make_article(
        db,
        user,
        slug="batman",
        article_type=ArticleType.profile,
        metadata_=PROFILE_META,
        status=source_status,
    )
    index: AliasIndex = {"gotham": target.id}
    await sync_wikilink_edges(source.id, "[[gotham]]", index, db)
    await db.commit()
    article_id = source.id if article_role == "source" else target.id
    assert await fetch_fn(article_id, db) == []


# --- backfill_on_publish ---


@pytest.mark.parametrize(
    ("source_content", "target_content", "expect_resolve"),
    [
        pytest.param("[[Avengers]]", "", True, id="resolves-wikilinks"),
        pytest.param("", "[[Avengers]]", False, id="ignores-self"),
    ],
)
async def test_backfill_on_publish(
    db: AsyncSession,
    user: User,
    source_content: str,
    target_content: str,
    expect_resolve: bool,
) -> None:
    """Publish backfill resolves wikilinks in other articles; does not self-link."""
    target = await make_article(
        db,
        user,
        slug="avengers",
        article_type=ArticleType.org,
        metadata_=ORG_META,
        content=target_content,
    )
    source = await make_article(
        db,
        user,
        slug="iron-man",
        article_type=ArticleType.profile,
        metadata_=PROFILE_META,
        content=source_content,
    )
    await backfill_on_publish(target.id, db)
    await db.commit()
    checked_id = source.id if expect_resolve else target.id
    assert len(await _get_wikilink_edges(db, checked_id)) == int(expect_resolve)


# --- backfill_on_alias_change ---


@pytest.mark.parametrize(
    ("old_aliases", "new_aliases", "pre_populate", "expect_edge"),
    [
        pytest.param([], ["iron man"], False, True, id="added-resolves"),
        pytest.param(["iron man"], [], True, False, id="removed-deletes"),
    ],
)
async def test_backfill_on_alias_change(
    db: AsyncSession,
    user: User,
    old_aliases: list[str],
    new_aliases: list[str],
    pre_populate: bool,
    expect_edge: bool,
) -> None:
    """Alias additions resolve wikilink edges; alias removals delete them."""
    old_meta = {**PROFILE_META, "aliases": old_aliases}
    new_meta = {**PROFILE_META, "aliases": new_aliases}
    target = await make_article(
        db,
        user,
        slug="tony-stark",
        article_type=ArticleType.profile,
        metadata_=new_meta,
    )
    source = await make_article(
        db,
        user,
        slug="source",
        article_type=ArticleType.org,
        metadata_=ORG_META,
        content="[[Iron Man]]",
    )
    if pre_populate:
        await sync_wikilink_edges(
            source.id, source.content, {"iron man": target.id}, db
        )
        await db.commit()
    await backfill_on_alias_change(
        target.id, old_meta, new_meta, ArticleType.profile, db
    )
    await db.commit()
    assert (len(await _get_wikilink_edges(db, source.id)) > 0) == expect_edge


async def test_backfill_on_publish_via_alias(db: AsyncSession, user: User) -> None:
    """Publish backfill resolves wikilinks that reference the article by an alias."""
    target = await make_article(
        db,
        user,
        slug="tony-stark",
        article_type=ArticleType.profile,
        metadata_={**PROFILE_META, "aliases": ["iron man"]},
    )
    source = await make_article(
        db,
        user,
        slug="source",
        article_type=ArticleType.org,
        metadata_=ORG_META,
        content="[[Iron Man]]",
    )
    await backfill_on_publish(target.id, db)
    await db.commit()
    assert await _get_wikilink_edges(db, source.id) == [
        {"target_id": target.id, "field_name": None, "resolved_via": "iron man"}
    ]


async def test_find_articles_referencing_empty_set(
    db: AsyncSession, user: User
) -> None:
    """Empty alias set returns immediately without querying."""
    assert await _find_articles_referencing(set(), 0, db) == []


async def test_backfill_on_alias_change_noop_for_type_without_aliases(
    db: AsyncSession, user: User
) -> None:
    """backfill_on_alias_change is a no-op for article types with no alias fields."""
    await backfill_on_alias_change(999, {}, {}, ArticleType.event, db)


# --- fetch_org_members ---


@pytest.fixture
async def org_members_setup(db: AsyncSession, user: User) -> Article:
    """Org with two affiliated published profiles: active cap, retired war-machine."""
    org = await make_article(
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=ORG_META
    )
    active = await make_article(
        db,
        user,
        slug="captain-america",
        article_type=ArticleType.profile,
        designation="CAPE-0001",
        metadata_={**PROFILE_META, "status": "active", "aliases": ["Cap"]},
    )
    retired = await make_article(
        db,
        user,
        slug="war-machine",
        article_type=ArticleType.profile,
        metadata_={**PROFILE_META, "status": "retired"},
    )
    index: AliasIndex = {"avengers": org.id}
    for profile in (active, retired):
        await sync_metadata_edges(
            profile.id,
            ArticleType.profile,
            {**PROFILE_META, "affiliation": ["avengers"]},
            index,
            db,
        )
    await db.commit()
    return org


@pytest.mark.parametrize(
    ("idx", "expected"),
    [
        pytest.param(
            0,
            {
                "slug": "captain-america",
                "designation": "CAPE-0001",
                "status": "active",
                "aliases": ["Cap"],
            },
            id="active-member-fields",
        ),
        pytest.param(
            1,
            {
                "slug": "war-machine",
                "designation": None,
                "status": "retired",
                "aliases": [],
            },
            id="retired-member-ordered-after-active",
        ),
    ],
)
async def test_fetch_org_members(
    db: AsyncSession, org_members_setup: Article, idx: int, expected: dict
) -> None:
    """Members appear in status-then-slug order with correct field shape."""
    members = await fetch_org_members(org_members_setup.id, db)
    assert members[idx] == expected


@pytest.mark.parametrize("status", [ArticleStatus.draft, ArticleStatus.pending])
async def test_fetch_org_members_excludes_unpublished(
    db: AsyncSession, user: User, status: ArticleStatus
) -> None:
    """Affiliated profiles that are not published are excluded from the roster."""
    org = await make_article(
        db, user, slug="avengers", article_type=ArticleType.org, metadata_=ORG_META
    )
    profile = await make_article(
        db,
        user,
        slug="ghost",
        article_type=ArticleType.profile,
        metadata_=PROFILE_META,
        status=status,
    )
    await sync_metadata_edges(
        profile.id,
        ArticleType.profile,
        {**PROFILE_META, "affiliation": ["avengers"]},
        {"avengers": org.id},
        db,
    )
    await db.commit()
    assert await fetch_org_members(org.id, db) == []
