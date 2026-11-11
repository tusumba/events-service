import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common import ApiError, CurrentUser

from app.models import Event, EventVersion
from app.repositories.events import EventFilters, EventRepository
from app.schemas.events import EventCard, EventCardPage, EventDetail, Money, Organizer

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


def _organizer(event: Event) -> Organizer:
    # club_name появится вместе с таблицей clubs (#19045).
    if event.club_id is not None:
        return Organizer(type="club", club_id=event.club_id)
    return Organizer(type="user", user_id=event.created_by_user_id)


def _user_uuid(user: CurrentUser | None) -> uuid.UUID | None:
    if user is None:
        return None
    try:
        return uuid.UUID(user.id)
    except ValueError:
        return None


async def get_event(
    session: AsyncSession, event_id: uuid.UUID, user: CurrentUser | None
) -> EventDetail:
    repository = EventRepository(session)
    found = await repository.get(event_id)
    if found is None:
        raise ApiError(404, "event_not_found", "Мероприятие недоступно.")
    event, version = found
    user_id = _user_uuid(user)
    my_role = None if user_id is None else await repository.member_role(event.id, user_id)
    return EventDetail(
        **to_card(event, version).model_dump(),
        description=version.description,
        organizer=_organizer(event),
        current_version_id=version.id,
        version_no=version.version_no,
        my_role=my_role,
    )
