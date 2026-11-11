import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventStatus, EventVersion, LifecycleStatus

TODAY = dt.date(2026, 11, 11)


async def add_event(
    session: AsyncSession,
    *,
    title: str = "Лекция",
    date: dt.date = TODAY,
    place_address: str = "Новосибирск, ул. Пирогова, 1",
    price: Decimal | None = None,
    status: EventStatus = EventStatus.CONFIRMED,
    club_id: uuid.UUID | None = None,
    deleted: bool = False,
) -> Event:
    event_id, version_id = uuid.uuid4(), uuid.uuid4()
    version = EventVersion(
        id=version_id,
        event_id=event_id,
        version_no=1,
        title=title,
        description=f"Описание: {title}",
        edited_by=uuid.uuid4(),
    )
    event = Event(
        id=event_id,
        current_version_id=version_id,
        created_by_user_id=version.edited_by,
        club_id=club_id,
        status=status,
        date=date,
        place_address=place_address,
        is_free=price is None,
        price=price,
    )
    if deleted:
        event.lifecycle_status = LifecycleStatus.DELETED
        event.deletion_reason = "Нарушение правил"
        event.deleted_by = uuid.uuid4()
        event.deleted_at = dt.datetime.now(dt.UTC)
    session.add_all([event, version])
    await session.flush()
    return event


async def add_version(session: AsyncSession, event: Event, title: str) -> EventVersion:
    version = EventVersion(
        event_id=event.id,
        version_no=2,
        title=title,
        description=f"Описание: {title}",
        edited_by=event.created_by_user_id,
    )
    session.add(version)
    await session.flush()
    event.current_version_id = version.id
    await session.flush()
    return version
