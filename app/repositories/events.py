import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Event,
    EventStatus,
    EventTeamMember,
    EventVersion,
    LifecycleStatus,
    TeamRole,
)


@dataclass(frozen=True)
class EventFilters:
    date_from: dt.date
    date_to: dt.date | None = None
    is_free: bool | None = None
    place: str | None = None
    statuses: Sequence[EventStatus] = field(default_factory=tuple)


def _contains(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _conditions(filters: EventFilters) -> list[ColumnElement[bool]]:
    conditions = [Event.date >= filters.date_from]
    if filters.date_to is not None:
        conditions.append(Event.date <= filters.date_to)
    if filters.is_free is not None:
        conditions.append(Event.is_free.is_(filters.is_free))
    if filters.place:
        conditions.append(Event.place_address.ilike(_contains(filters.place), escape="\\"))
    if filters.statuses:
        conditions.append(Event.status.in_(filters.statuses))
    return conditions


def _with_current_version() -> Select[Event, EventVersion]:
    return (
        select(Event, EventVersion)
        .join(EventVersion, EventVersion.id == Event.current_version_id)
        .where(Event.lifecycle_status == LifecycleStatus.ACTIVE)
    )


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def catalog(
        self, filters: EventFilters, offset: int, limit: int
    ) -> tuple[list[tuple[Event, EventVersion]], int]:
        base = _with_current_version().where(*_conditions(filters))
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self._session.execute(
            base.order_by(Event.date, Event.id).offset(offset).limit(limit)
        )
        return [(event, version) for event, version in rows], total or 0

    async def get(self, event_id: uuid.UUID) -> tuple[Event, EventVersion] | None:
        row = (
            await self._session.execute(_with_current_version().where(Event.id == event_id))
        ).first()
        return None if row is None else (row[0], row[1])

    async def member_role(self, event_id: uuid.UUID, user_id: uuid.UUID) -> TeamRole | None:
        return await self._session.scalar(
            select(EventTeamMember.role).where(
                EventTeamMember.event_id == event_id, EventTeamMember.user_id == user_id
            )
        )
