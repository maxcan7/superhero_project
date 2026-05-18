"""article_links.

Revision ID: b1c3e7f9a2d4
Revises: a2b5d7e9f1c3
Create Date: 2026-05-18 00:00:02.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c3e7f9a2d4"
down_revision: str | Sequence[str] | None = "a2b5d7e9f1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "article_links",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.BigInteger(),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("resolved_via", sa.String(255), nullable=True),
        sa.UniqueConstraint(
            "source_id", "target_id", "field_name", name="uq_article_links"
        ),
    )
    op.create_index("article_links_source_idx", "article_links", ["source_id"])
    op.create_index("article_links_target_idx", "article_links", ["target_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("article_links_target_idx", table_name="article_links")
    op.drop_index("article_links_source_idx", table_name="article_links")
    op.drop_table("article_links")
