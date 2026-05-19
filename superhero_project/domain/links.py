"""Link graph domain logic: alias index, wikilink parser, and edge extraction."""

import re

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

        if article.article_type != ArticleType.disambiguation:
            index[normalize_str(article.slug)] = article.id

        if article.article_type == ArticleType.profile:
            if article.designation:
                index[normalize_str(article.designation)] = article.id
            for alias in article.metadata_.get("aliases", []):
                index[normalize_str(alias)] = article.id

        elif article.article_type == ArticleType.org:
            for alias in article.metadata_.get("aliases", []):
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
            return f'<a href="/articles/{slug}">{display}</a>'
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
