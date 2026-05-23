"""add_publisher_org_type.

Revision ID: f3a8c91d2e47
Revises: e8cd183be506
Create Date: 2026-05-18 00:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f3a8c91d2e47"
down_revision: str | Sequence[str] | None = "e8cd183be506"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
