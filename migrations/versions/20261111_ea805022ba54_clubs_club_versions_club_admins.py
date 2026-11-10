"""clubs, club_versions, club_admins

Revision ID: ea805022ba54
Revises:
Create Date: 2026-11-11 01:01:38.694436
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models import SCHEMA

revision: str = "ea805022ba54"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

club_status = postgresql.ENUM(
    "published", "blocked", name="club_status", schema=SCHEMA, create_type=False
)


def upgrade() -> None:
    # Расширение общее для всех схем базы, как в deploy/postgres/init.sh.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public")
    club_status.create(op.get_bind())

    op.create_table(
        "clubs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", club_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clubs")),
        schema=SCHEMA,
    )
    op.create_table(
        "club_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("club_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("meeting_place", sa.Text(), nullable=True),
        sa.Column("schedule", sa.Text(), nullable=True),
        sa.Column(
            "contacts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("photo_path", sa.Text(), nullable=True),
        sa.Column("edited_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["club_id"],
            [f"{SCHEMA}.clubs.id"],
            name=op.f("fk_club_versions_club_id_clubs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_club_versions")),
        sa.UniqueConstraint(
            "club_id", "version_no", name=op.f("uq_club_versions_club_id_version_no")
        ),
        schema=SCHEMA,
    )
    # Секция и её первая версия ссылаются друг на друга: проверка откладывается до коммита.
    op.create_foreign_key(
        op.f("fk_clubs_current_version_id_club_versions"),
        "clubs",
        "club_versions",
        ["current_version_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "club_admins",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("club_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["club_id"],
            [f"{SCHEMA}.clubs.id"],
            name=op.f("fk_club_admins_club_id_clubs"),
        ),
        sa.PrimaryKeyConstraint("user_id", "club_id", name=op.f("pk_club_admins")),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_club_versions_lower_name_trgm",
        "club_versions",
        [sa.text("lower(name) gin_trgm_ops")],
        postgresql_using="gin",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_clubs_published_current_version_id",
        "clubs",
        ["current_version_id"],
        postgresql_where=sa.text("status = 'published'"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_clubs_published_current_version_id", table_name="clubs", schema=SCHEMA)
    op.drop_index("ix_club_versions_lower_name_trgm", table_name="club_versions", schema=SCHEMA)
    op.drop_table("club_admins", schema=SCHEMA)
    op.drop_constraint(
        op.f("fk_clubs_current_version_id_club_versions"),
        "clubs",
        type_="foreignkey",
        schema=SCHEMA,
    )
    op.drop_table("club_versions", schema=SCHEMA)
    op.drop_table("clubs", schema=SCHEMA)
    club_status.drop(op.get_bind())
    # pg_trgm не удаляется: расширение общее для всей базы, его ставит deploy/postgres/init.sh.
