import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventVersion, LifecycleStatus


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def catalog(
        self, date_from: dt.date, offset: int, limit: int
    ) -> tuple[list[tuple[Event, EventVersion]], int]:
        base = (
            select(Event, EventVersion)
            .join(EventVersion, EventVersion.id == Event.current_version_id)
            .where(Event.lifecycle_status == LifecycleStatus.ACTIVE, Event.date >= date_from)
        )
        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = await self._session.execute(
            base.order_by(Event.date, Event.id).offset(offset).limit(limit)
        )
        return [(event, version) for event, version in rows], total or 0
