"""Link graph domain logic: alias index, wikilink parser, and edge extraction."""

import re
from dataclasses import dataclass
from dataclasses import field

from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.domain._utils import normalize_str

AliasIndex = dict[str, int]  # normalized text → article_id
SlugMap = dict[int, str]  # article_id → slug

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]")


@dataclass
class TypeHandler:
    """Per-type config shared by alias extraction and metadata edge extraction."""

    # Metadata keys whose list values are additional aliases for the index
    alias_fields: list[str] = field(default_factory=list)
    # True if article.designation should also be indexed
    index_designation: bool = False
    # (field_name, metadata_key, is_list) — drives metadata edge extraction
    edge_fields: list[tuple[str, str, bool]] = field(default_factory=list)


_HANDLERS: dict[ArticleType, TypeHandler] = {
    ArticleType.profile: TypeHandler(
        alias_fields=["aliases"],
        index_designation=True,
        edge_fields=[
            ("affiliation", "affiliation", True),
            ("base_of_operations", "base_of_operations", False),
        ],
    ),
    ArticleType.event: TypeHandler(
        edge_fields=[
            ("location", "location", False),
            ("participants", "participants", True),
        ],
    ),
    ArticleType.org: TypeHandler(
        alias_fields=["aliases"],
        edge_fields=[
            ("headquarters", "headquarters", False),
            ("affiliation", "affiliation", True),
        ],
    ),
    ArticleType.location: TypeHandler(
        edge_fields=[
            ("notable_residents", "notable_residents", True),
        ],
    ),
    ArticleType.tech: TypeHandler(
        edge_fields=[
            ("current_holder", "current_holder", False),
        ],
    ),
    ArticleType.lore: TypeHandler(
        edge_fields=[
            ("related_articles", "related_articles", True),
        ],
    ),
    ArticleType.comic: TypeHandler(
        edge_fields=[
            ("publishers", "publishers", True),
        ],
    ),
}


async def build_link_maps(db: AsyncSession) -> tuple[AliasIndex, SlugMap]:
    """Build alias index and slug map for all published articles in one query."""
    result = await db.execute(
        select(Article).where(Article.status == ArticleStatus.published)
    )
    articles = result.scalars().all()

    index: AliasIndex = {}
    slug_map: SlugMap = {}

    for article in articles:
        slug_map[article.id] = article.slug

        index[normalize_str(article.slug)] = article.id

        handler = _HANDLERS.get(article.article_type)
        if handler is None:
            continue

        if handler.index_designation and article.designation:
            index[normalize_str(article.designation)] = article.id

        for alias_field in handler.alias_fields:
            for alias in article.metadata_.get(alias_field, []):
                index[normalize_str(alias)] = article.id

    return index, slug_map


async def build_alias_index(db: AsyncSession) -> AliasIndex:
    """Map normalized alias strings to article IDs for all published articles."""
    index, _ = await build_link_maps(db)
    return index


def render_wikilinks(content: str, index: AliasIndex, slug_map: SlugMap) -> str:
    """Replace [[...]] patterns with HTML links; unresolved targets become red-links."""

    def _replace(m: re.Match[str]) -> str:
        """Render one [[...]] match as a resolved anchor or a red-link."""
        target = m.group(1)
        display = m.group(2) or target
        normalized = normalize_str(target)
        article_id = index.get(normalized)
        if article_id is not None:
            slug = slug_map[article_id]
            return f'<a href="/articles/{slug}/view">{display}</a>'
        return (
            f'<a href="/articles/new?slug={normalized}" class="red-link">{target}</a>'
        )

    return _WIKILINK_RE.sub(_replace, content)


async def sync_wikilink_edges(
    source_id: int, content: str, index: AliasIndex, db: AsyncSession
) -> None:
    """Replace wikilink edges for source: delete stale ones, insert freshly resolved."""
    await db.execute(
        text(
            "DELETE FROM article_links"
            " WHERE source_id = :source_id AND field_name IS NULL"
        ),
        {"source_id": source_id},
    )

    # Deduplicate: one edge per target (last alias wins if same target appears twice)
    edges: dict[int, str] = {}
    for m in _WIKILINK_RE.finditer(content):
        normalized = normalize_str(m.group(1))
        target_id = index.get(normalized)
        if target_id is not None:
            edges[target_id] = normalized

    for target_id, resolved_via in edges.items():
        await db.execute(
            text(
                "INSERT INTO article_links"
                " (source_id, target_id, field_name, resolved_via)"
                " VALUES (:source_id, :target_id, NULL, :resolved_via)"
            ),
            {
                "source_id": source_id,
                "target_id": target_id,
                "resolved_via": resolved_via,
            },
        )


def _extract_metadata_edges(
    article_type: ArticleType,
    metadata: dict[str, str | list[str] | None],
    index: AliasIndex,
) -> list[tuple[int, str, str]]:
    """Return resolved metadata edges as (target_id, field_name, resolved_via)
    triples."""
    handler = _HANDLERS.get(article_type)
    if handler is None:
        return []

    # Deduplicate by (target_id, field_name): last resolved alias wins
    seen = {}  # (target_id, field_name) → resolved_via
    for edge_field_name, meta_key, is_list in handler.edge_fields:
        value = metadata.get(meta_key)
        if value is None:
            continue
        values: list[str] = value if isinstance(value, list) else [value]
        for v in values:
            normalized = normalize_str(v)
            target_id = index.get(normalized)
            if target_id is not None:
                seen[target_id, edge_field_name] = normalized

    return [(tid, fname, via) for (tid, fname), via in seen.items()]


async def fetch_outgoing_links(
    article_id: int, db: AsyncSession
) -> list[dict[str, str | None]]:
    """Return outgoing edges for an article: resolved wikilinks and metadata edges."""
    rows = await db.execute(
        text(
            "SELECT a.slug, a.article_type, al.field_name, al.resolved_via"
            " FROM article_links al JOIN articles a ON a.id = al.target_id"
            " WHERE al.source_id = :id AND a.status = 'published'"
            " ORDER BY al.field_name NULLS FIRST, a.article_type"
        ),
        {"id": article_id},
    )
    return [
        {
            "slug": r.slug,
            "article_type": r.article_type,
            "field_name": r.field_name,
            "resolved_via": r.resolved_via,
        }
        for r in rows
    ]


async def fetch_org_members(org_id: int, db: AsyncSession) -> list[dict[str, object]]:
    """Return published profiles whose affiliation edge points to this org."""
    rows = await db.execute(
        text(
            "SELECT a.slug, a.designation,"
            " a.metadata->>'status' AS status,"
            " a.metadata->'aliases' AS aliases"
            " FROM article_links al JOIN articles a ON a.id = al.source_id"
            " WHERE al.target_id = :org_id"
            " AND al.field_name = 'affiliation'"
            " AND a.article_type = 'profile'"
            " AND a.status = 'published'"
            " ORDER BY a.metadata->>'status', a.slug"
        ),
        {"org_id": org_id},
    )
    return [
        {
            "slug": r.slug,
            "designation": r.designation,
            "status": r.status or "unknown",
            "aliases": r.aliases or [],
        }
        for r in rows
    ]


async def fetch_location_activity(
    location_id: int, db: AsyncSession
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return (events, residents) for a location derived from article_links."""
    event_rows = await db.execute(
        text(
            "SELECT a.slug, a.metadata->>'event_date' AS event_date,"
            " a.metadata->>'outcome' AS outcome"
            " FROM article_links al JOIN articles a ON a.id = al.source_id"
            " WHERE al.target_id = :location_id"
            " AND al.field_name = 'location'"
            " AND a.article_type = 'event'"
            " AND a.status = 'published'"
            " ORDER BY a.metadata->>'event_date'"
        ),
        {"location_id": location_id},
    )
    events = [
        {"slug": r.slug, "event_date": r.event_date, "outcome": r.outcome}
        for r in event_rows
    ]

    resident_rows = await db.execute(
        text(
            "SELECT a.slug, a.designation, a.metadata->>'status' AS status"
            " FROM article_links al JOIN articles a ON a.id = al.source_id"
            " WHERE al.target_id = :location_id"
            " AND al.field_name = 'base_of_operations'"
            " AND a.article_type = 'profile'"
            " AND a.status = 'published'"
        ),
        {"location_id": location_id},
    )
    residents = [
        {"slug": r.slug, "designation": r.designation, "status": r.status or "unknown"}
        for r in resident_rows
    ]

    return events, residents


async def fetch_incoming_links(
    article_id: int, db: AsyncSession
) -> list[dict[str, str | None]]:
    """Return incoming edges for an article: articles that link here."""
    rows = await db.execute(
        text(
            "SELECT a.slug, a.article_type, al.field_name"
            " FROM article_links al JOIN articles a ON a.id = al.source_id"
            " WHERE al.target_id = :id AND a.status = 'published'"
            " ORDER BY a.article_type, al.field_name NULLS FIRST"
        ),
        {"id": article_id},
    )
    return [
        {"slug": r.slug, "article_type": r.article_type, "field_name": r.field_name}
        for r in rows
    ]


def _article_aliases(
    article_type: ArticleType,
    slug: str,
    designation: str | None,
    metadata: dict[str, str | list[str] | None],
) -> set[str]:
    """Return all normalized alias strings for an article."""
    aliases = {normalize_str(slug)}
    handler = _HANDLERS.get(article_type)
    if handler:
        if handler.index_designation and designation:
            aliases.add(normalize_str(designation))
        for alias_field in handler.alias_fields:
            value = metadata.get(alias_field)
            if isinstance(value, list):
                for alias in value:
                    aliases.add(normalize_str(alias))
    return aliases


async def _find_articles_referencing(
    aliases: set[str], exclude_id: int, db: AsyncSession
) -> list[Article]:
    """Find published articles whose content contains any of the given alias strings."""
    if not aliases:
        return []
    result = await db.execute(
        select(Article)
        .where(Article.status == ArticleStatus.published)
        .where(Article.id != exclude_id)
        .where(or_(*(Article.content.ilike(f"%{alias}%") for alias in aliases)))
    )
    return list(result.scalars().all())


async def backfill_on_publish(article_id: int, db: AsyncSession) -> None:
    """Re-resolve wikilink edges in other articles that can now resolve to this one."""
    article = (
        await db.execute(select(Article).where(Article.id == article_id))
    ).scalar_one()
    aliases = _article_aliases(
        article.article_type, article.slug, article.designation, article.metadata_
    )
    index, _ = await build_link_maps(db)
    for candidate in await _find_articles_referencing(aliases, article_id, db):
        await sync_wikilink_edges(candidate.id, candidate.content, index, db)


async def backfill_on_alias_change(
    article_id: int,
    old_metadata: dict[str, str | list[str] | None],
    new_metadata: dict[str, str | list[str] | None],
    article_type: ArticleType,
    db: AsyncSession,
) -> None:
    """Handle wikilink edge changes caused by alias additions or removals."""
    handler = _HANDLERS.get(article_type)
    if handler is None or not handler.alias_fields:
        return

    old_aliases: set[str] = set()
    new_aliases: set[str] = set()
    for alias_field in handler.alias_fields:
        old_val = old_metadata.get(alias_field)
        new_val = new_metadata.get(alias_field)
        if isinstance(old_val, list):
            old_aliases.update(normalize_str(a) for a in old_val)
        if isinstance(new_val, list):
            new_aliases.update(normalize_str(a) for a in new_val)

    added = new_aliases - old_aliases
    removed = old_aliases - new_aliases

    if added:
        index, _ = await build_link_maps(db)
        for candidate in await _find_articles_referencing(added, article_id, db):
            await sync_wikilink_edges(candidate.id, candidate.content, index, db)

    for alias in removed:
        await db.execute(
            text(
                "DELETE FROM article_links"
                " WHERE target_id = :article_id AND resolved_via = :alias"
            ),
            {"article_id": article_id, "alias": alias},
        )


async def sync_metadata_edges(
    source_id: int,
    article_type: ArticleType,
    metadata: dict[str, str | list[str] | None],
    index: AliasIndex,
    db: AsyncSession,
) -> None:
    """Replace metadata edges for source: delete stale ones, insert freshly resolved."""
    await db.execute(
        text(
            "DELETE FROM article_links"
            " WHERE source_id = :source_id AND field_name IS NOT NULL"
        ),
        {"source_id": source_id},
    )

    for target_id, field_name, resolved_via in _extract_metadata_edges(
        article_type, metadata, index
    ):
        await db.execute(
            text(
                "INSERT INTO article_links"
                " (source_id, target_id, field_name, resolved_via)"
                " VALUES (:source_id, :target_id, :field_name, :resolved_via)"
                " ON CONFLICT (source_id, target_id, field_name)"
                " DO UPDATE SET resolved_via = EXCLUDED.resolved_via"
            ),
            {
                "source_id": source_id,
                "target_id": target_id,
                "field_name": field_name,
                "resolved_via": resolved_via,
            },
        )
