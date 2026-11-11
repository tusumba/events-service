"""events, event_versions

Revision ID: d1227d8ef185
Revises:
Create Date: 2026-11-11 02:55:20.838004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models import SCHEMA

revision: str = "d1227d8ef185"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

event_status = postgresql.ENUM(
    "not_confirmed",
    "confirmed",
    "held",
    "not_held",
    name="event_status",
    schema=SCHEMA,
    create_type=False,
)


def upgrade() -> None:
    event_status.create(op.get_bind())

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("club_id", sa.Uuid(), nullable=True),
        sa.Column("organizer_name", sa.String(length=255), nullable=True),
        sa.Column("status", event_status, server_default="confirmed", nullable=False),
        sa.Column(
            "lifecycle_status", sa.String(length=16), server_default="active", nullable=False
        ),
        sa.Column("deletion_reason", sa.Text(), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("place_address", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("is_free", sa.Boolean(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(is_free AND price IS NULL) OR (NOT is_free AND price IS NOT NULL AND price > 0)",
            name=op.f("ck_events_price_matches_is_free"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)", name=op.f("ck_events_coordinates_pair")
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'deleted')", name=op.f("ck_events_lifecycle_status")
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'active' AND deletion_reason IS NULL AND deleted_by IS NULL"
            " AND deleted_at IS NULL) OR (lifecycle_status = 'deleted'"
            " AND deletion_reason IS NOT NULL AND deleted_by IS NOT NULL"
            " AND deleted_at IS NOT NULL)",
            name=op.f("ck_events_deletion_matches_lifecycle"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_events_club_id"), "events", ["club_id"], schema=SCHEMA)
    op.create_index(
        "ix_events_active_date_id",
        "events",
        ["date", "id"],
        postgresql_where=sa.text("lifecycle_status = 'active'"),
        schema=SCHEMA,
    )

    op.create_table(
        "event_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("edited_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version_no >= 1", name=op.f("ck_event_versions_version_no_positive")),
        sa.ForeignKeyConstraint(
            ["event_id"], [f"{SCHEMA}.events.id"], name=op.f("fk_event_versions_event_id_events")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_versions")),
        sa.UniqueConstraint("event_id", "id", name=op.f("uq_event_versions_event_id_id")),
        sa.UniqueConstraint(
            "event_id", "version_no", name=op.f("uq_event_versions_event_id_version_no")
        ),
        schema=SCHEMA,
    )
    # Мероприятие и его первая версия ссылаются друг на друга: проверка откладывается до коммита.
    op.create_foreign_key(
        op.f("fk_events_id_current_version_id_event_versions"),
        "events",
        "event_versions",
        ["id", "current_version_id"],
        ["event_id", "id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_events_id_current_version_id_event_versions"),
        "events",
        type_="foreignkey",
        schema=SCHEMA,
    )
    op.drop_table("event_versions", schema=SCHEMA)
    op.drop_index("ix_events_active_date_id", table_name="events", schema=SCHEMA)
    op.drop_index(op.f("ix_events_club_id"), table_name="events", schema=SCHEMA)
    op.drop_table("events", schema=SCHEMA)
    event_status.drop(op.get_bind())
