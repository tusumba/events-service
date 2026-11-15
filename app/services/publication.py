import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_contracts import ApplicationApproved, BaseEvent, EventEnvelope, EventPublished

from app.events import enqueue_event
from app.models import Event, EventStatus, EventTeamMember, EventVersion, TeamRole

logger = logging.getLogger(__name__)


async def handle_application_approved(
    session: AsyncSession, envelope: EventEnvelope[BaseEvent]
) -> None:
    """Создать мероприятие по одобренной заявке, назначить автора владельцем, опубликовать.

    Вызывается из process_event: повтор того же event_id сюда не доходит, а изменения
    и запись в журнал processed_events фиксируются одной транзакцией.
    """
    approved = envelope.payload
    if not isinstance(approved, ApplicationApproved):
        logger.warning("В очередь заявок пришло %s, пропущено", envelope.event_type)
        return
    if approved.type != "event" or approved.event is None:
        # Страницы секций создаются в #19047.
        return
    existing = await session.scalar(select(Event.id).where(Event.id == approved.result_object_id))
    if existing is not None:
        logger.info("Мероприятие %s уже создано", approved.result_object_id)
        return

    data = approved.event
    price = None if data.is_free or data.price is None else data.price
    version_id = uuid.uuid4()
    event = Event(
        id=approved.result_object_id,
        current_version_id=version_id,
        created_by_user_id=approved.author_user_id,
        club_id=approved.club_id,
        status=EventStatus.CONFIRMED,
        date=data.date,
        place_address=data.place_address,
        is_free=data.is_free,
        price=None if price is None else Decimal(price.amount) / 100,
    )
    version = EventVersion(
        id=version_id,
        event_id=event.id,
        version_no=1,
        title=data.title,
        description=data.description,
        edited_by=approved.author_user_id,
    )
    owner = EventTeamMember(event_id=event.id, user_id=approved.author_user_id, role=TeamRole.OWNER)
    session.add_all([event, version, owner])
    await session.flush()
    enqueue_event(
        session,
        EventPublished(
            event_id=event.id,
            current_version_id=version_id,
            title=data.title,
            date=data.date,
            place_address=data.place_address,
            is_free=data.is_free,
            price=price,
            status="confirmed",
            club_id=approved.club_id,
            created_by_user_id=approved.author_user_id,
        ),
    )
    logger.info("Мероприятие %s создано по заявке %s", event.id, approved.application_id)
