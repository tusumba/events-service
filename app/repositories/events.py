import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventStatus, EventVersion, LifecycleStatus


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
    conditions = [
        Event.lifecycle_status == LifecycleStatus.ACTIVE,
        Event.date >= filters.date_from,
    ]
    if filters.date_to is not None:
        conditions.append(Event.date <= filters.date_to)
    if filters.is_free is not None:
        conditions.append(Event.is_free.is_(filters.is_free))
    if filters.place:
        conditions.append(Event.place_address.ilike(_contains(filters.place), escape="\\"))
    if filters.statuses:
        conditions.append(Event.status.in_(filters.statuses))
    return conditions


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def catalog(
        self, filters: EventFilters, offset: int, limit: int
    ) -> tuple[list[tuple[Event, EventVersion]], int]:
        base = (
            select(Event, EventVersion)
            .join(EventVersion, EventVersion.id == Event.current_version_id)
            .where(*_conditions(filters))
        )
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self._session.execute(
            base.order_by(Event.date, Event.id).offset(offset).limit(limit)
        )
        return [(event, version) for event, version in rows], total or 0
