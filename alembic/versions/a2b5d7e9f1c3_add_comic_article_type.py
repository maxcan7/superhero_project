"""add_comic_article_type.

Revision ID: a2b5d7e9f1c3
Revises: f3a8c91d2e47
Create Date: 2026-05-18 00:00:01.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b5d7e9f1c3"
down_revision: str | Sequence[str] | None = "f3a8c91d2e47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE article_type ADD VALUE IF NOT EXISTS 'comic'")
    op.execute("ALTER TYPE article_type ADD VALUE IF NOT EXISTS 'disambiguation'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
