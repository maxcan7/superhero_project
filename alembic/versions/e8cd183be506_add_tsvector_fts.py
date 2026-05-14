"""add_tsvector_fts.

Revision ID: e8cd183be506
Revises: 243360e2b03e
Create Date: 2026-05-14 11:24:16.754642
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8cd183be506"
down_revision: str | Sequence[str] | None = "243360e2b03e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER_FUNC = """
CREATE OR REPLACE FUNCTION articles_fts_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.slug, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.content, '')), 'B');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""

_TRIGGER = """
CREATE TRIGGER articles_fts_trigger
BEFORE INSERT OR UPDATE OF slug, content
ON articles
FOR EACH ROW EXECUTE FUNCTION articles_fts_update();
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "articles",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index(
        "ix_articles_search_vector",
        "articles",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.execute(_TRIGGER_FUNC)
    op.execute(_TRIGGER)
    op.execute(
        """UPDATE articles SET search_vector = setweight(to_tsvector('english',
        coalesce(slug, '')), 'A') || setweight(to_tsvector('english', coalesce(content,
        '')), 'B')"""
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS articles_fts_trigger ON articles")
    op.execute("DROP FUNCTION IF EXISTS articles_fts_update()")
    op.drop_index("ix_articles_search_vector", table_name="articles")
    op.drop_column("articles", "search_vector")
