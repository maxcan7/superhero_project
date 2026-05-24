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


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("articles", "slug", new_column_name="page_name")
    op.drop_column("articles", "designation")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("articles", "page_name", new_column_name="slug")
    op.add_column("articles", sa.Column("designation", sa.String(20), nullable=True))
