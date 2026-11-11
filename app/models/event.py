import datetime as dt
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventStatus(StrEnum):
    NOT_CONFIRMED = "not_confirmed"
    CONFIRMED = "confirmed"
    HELD = "held"
    NOT_HELD = "not_held"


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        # Мероприятие и его первая версия ссылаются друг на друга: проверка откладывается
        # до коммита. Составной ключ не даёт указать версию чужого мероприятия.
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["event_versions.event_id", "event_versions.id"],
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(is_free AND price IS NULL) OR (NOT is_free AND price IS NOT NULL AND price > 0)",
            name="price_matches_is_free",
        ),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coordinates_pair"),
        CheckConstraint("lifecycle_status IN ('active', 'deleted')", name="lifecycle_status"),
        CheckConstraint(
            "(lifecycle_status = 'active' AND deletion_reason IS NULL AND deleted_by IS NULL"
            " AND deleted_at IS NULL) OR (lifecycle_status = 'deleted'"
            " AND deletion_reason IS NOT NULL AND deleted_by IS NOT NULL"
            " AND deleted_at IS NOT NULL)",
            name="deletion_matches_lifecycle",
        ),
        Index(
            "ix_events_active_date_id",
            "date",
            "id",
            postgresql_where=text("lifecycle_status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    current_version_id: Mapped[uuid.UUID]
    created_by_user_id: Mapped[uuid.UUID]
    # FK на clubs.id появится вместе с таблицей clubs (#19045).
    club_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    organizer_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", values_callable=lambda e: [m.value for m in e]),
        default=EventStatus.CONFIRMED,
        server_default=EventStatus.CONFIRMED.value,
    )
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        String(16), default=LifecycleStatus.ACTIVE, server_default=LifecycleStatus.ACTIVE.value
    )
    deletion_reason: Mapped[str | None] = mapped_column(Text)
    deleted_by: Mapped[uuid.UUID | None]
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date: Mapped[dt.date] = mapped_column(Date)
    place_address: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_free: Mapped[bool]
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventVersion(Base):
    __tablename__ = "event_versions"
    __table_args__ = (
        UniqueConstraint("event_id", "version_no"),
        UniqueConstraint("event_id", "id"),
        CheckConstraint("version_no >= 1", name="version_no_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"))
    version_no: Mapped[int]
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_fields: Mapped[list[str] | None] = mapped_column(JSONB)
    edited_by: Mapped[uuid.UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
