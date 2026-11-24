"""events.photo_path

Revision ID: c3e8a5d29f14
Revises: ea805022ba54
Create Date: 2026-11-25 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models import SCHEMA

revision: str = "c3e8a5d29f14"
down_revision: str | None = "ea805022ba54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("photo_path", sa.Text(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("events", "photo_path", schema=SCHEMA)
