"""add_publisher_org_type.

Revision ID: f3a8c91d2e47
Revises: e8cd183be506
Create Date: 2026-05-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8c91d2e47"
down_revision: str | Sequence[str] | None = "e8cd183be506"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE org_type ADD VALUE IF NOT EXISTS 'publisher'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not support removing enum values without recreating the type.
    pass
