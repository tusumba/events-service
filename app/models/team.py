import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TeamRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    SCANNER = "scanner"


class EventTeamMember(Base):
    """Участник команды мероприятия и его роль (OpenAPI Events, TeamRole)."""

    __tablename__ = "event_team_members"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[TeamRole] = mapped_column(
        Enum(TeamRole, name="team_role", values_callable=lambda e: [m.value for m in e])
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
