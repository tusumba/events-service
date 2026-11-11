"""event_team_members

Revision ID: a1c4e9f07b22
Revises: d1227d8ef185
Create Date: 2026-11-12 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models import SCHEMA

revision: str = "a1c4e9f07b22"
down_revision: str | None = "d1227d8ef185"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

team_role = postgresql.ENUM(
    "owner", "admin", "editor", "scanner", name="team_role", schema=SCHEMA, create_type=False
)


def upgrade() -> None:
    team_role.create(op.get_bind())
    op.create_table(
        "event_team_members",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", team_role, nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            [f"{SCHEMA}.events.id"],
            name=op.f("fk_event_team_members_event_id_events"),
        ),
        sa.PrimaryKeyConstraint("event_id", "user_id", name=op.f("pk_event_team_members")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("event_team_members", schema=SCHEMA)
    team_role.drop(op.get_bind())
