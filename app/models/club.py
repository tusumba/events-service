import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ClubStatus(StrEnum):
    PUBLISHED = "published"
    BLOCKED = "blocked"


class Club(Base):
    __tablename__ = "clubs"
    __table_args__ = (
        Index(
            "ix_clubs_published_current_version_id",
            "current_version_id",
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Ссылка на club_versions, а club_versions ссылается на clubs: связь отложена до коммита,
    # чтобы секцию и её первую версию можно было создать в одной транзакции.
    current_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("club_versions.id", use_alter=True, deferrable=True, initially="DEFERRED")
    )
    status: Mapped[ClubStatus] = mapped_column(
        Enum(ClubStatus, name="club_status", values_callable=lambda e: [m.value for m in e])
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClubVersion(Base):
    __tablename__ = "club_versions"
    __table_args__ = (
        UniqueConstraint("club_id", "version_no"),
        Index(
            "ix_club_versions_lower_name_trgm",
            func.lower(text("name")).label("lower_name"),
            postgresql_using="gin",
            postgresql_ops={"lower_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id"))
    version_no: Mapped[int]
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    meeting_place: Mapped[str | None] = mapped_column(Text)
    schedule: Mapped[str | None] = mapped_column(Text)
    contacts: Mapped[dict[str, str]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    photo_path: Mapped[str | None] = mapped_column(Text)
    edited_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClubAdmin(Base):
    __tablename__ = "club_admins"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id"), primary_key=True)
