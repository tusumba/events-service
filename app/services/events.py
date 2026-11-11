import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventVersion
from app.repositories.events import EventFilters, EventRepository
from app.schemas.events import EventCard, EventCardPage, Money

# «Сегодня» считается по Новосибирску (OpenAPI). Перехода на летнее время там нет с 2014 года.
NOVOSIBIRSK = dt.timezone(dt.timedelta(hours=7), "Asia/Novosibirsk")


def today_in_novosibirsk() -> dt.date:
    return dt.datetime.now(NOVOSIBIRSK).date()


def to_card(event: Event, version: EventVersion) -> EventCard:
    price = None if event.price is None else Money(amount=int(event.price * 100))
    return EventCard(
        id=event.id,
        title=version.title,
        date=event.date,
        place_address=event.place_address,
        is_free=event.is_free,
        price=price,
        status=event.status,
        club_id=event.club_id,
        photo_url=None,
    )


async def list_events(
    session: AsyncSession, filters: EventFilters, page: int, size: int
) -> EventCardPage:
    rows, total = await EventRepository(session).catalog(
        filters, offset=(page - 1) * size, limit=size
    )
    return EventCardPage(
        items=[to_card(event, version) for event, version in rows],
        total=total,
        page=page,
        size=size,
    )
