"""add_moderator_note_to_articles.

Revision ID: 902c17499866
Revises: 4fe5c7b33599
Create Date: 2026-05-27 14:15:12.367449
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "902c17499866"
down_revision: str | Sequence[str] | None = "4fe5c7b33599"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("articles", sa.Column("moderator_note", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("articles", "moderator_note")
