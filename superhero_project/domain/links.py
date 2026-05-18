"""Link graph domain logic: alias index, wikilink parser, and edge extraction."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superhero_project.db.models import Article
from superhero_project.db.models import ArticleStatus
from superhero_project.db.models import ArticleType
from superhero_project.domain._utils import normalize_str

AliasIndex = dict[str, int]  # normalized text → article_id


async def build_alias_index(db: AsyncSession) -> AliasIndex:
    """Map normalized alias strings to article IDs for all published articles."""
    result = await db.execute(
        select(Article).where(Article.status == ArticleStatus.published)
    )
    articles = result.scalars().all()

    index: AliasIndex = {}

    for article in articles:
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

    return index
