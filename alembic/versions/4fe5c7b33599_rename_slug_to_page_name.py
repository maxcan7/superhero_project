"""rename_slug_to_page_name.

Revision ID: 4fe5c7b33599
Revises: b1c3e7f9a2d4
Create Date: 2026-05-23 19:44:44.413431
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4fe5c7b33599"
down_revision: str | Sequence[str] | None = "b1c3e7f9a2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIGGER_FUNC_UP = """
CREATE OR REPLACE FUNCTION articles_fts_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.page_name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.content, '')), 'B');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""

_TRIGGER_UP = """
CREATE OR REPLACE TRIGGER articles_fts_trigger
BEFORE INSERT OR UPDATE OF page_name, content
ON articles
FOR EACH ROW EXECUTE FUNCTION articles_fts_update();
"""

_TRIGGER_FUNC_DOWN = """
CREATE OR REPLACE FUNCTION articles_fts_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector :=
    setweight(to_tsvector('english', coalesce(NEW.slug, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(NEW.content, '')), 'B');
  RETURN NEW;
END
$$ LANGUAGE plpgsql;
"""

_TRIGGER_DOWN = """
CREATE OR REPLACE TRIGGER articles_fts_trigger
BEFORE INSERT OR UPDATE OF slug, content
ON articles
FOR EACH ROW EXECUTE FUNCTION articles_fts_update();
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("articles", "slug", new_column_name="page_name")
    op.drop_column("articles", "designation")
    op.execute(_TRIGGER_FUNC_UP)
    op.execute(_TRIGGER_UP)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("articles", "page_name", new_column_name="slug")
    op.add_column("articles", sa.Column("designation", sa.String(20), nullable=True))
    op.execute(_TRIGGER_FUNC_DOWN)
    op.execute(_TRIGGER_DOWN)
