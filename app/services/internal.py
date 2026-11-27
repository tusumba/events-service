"""Данные мероприятий и секций для других сервисов (#19428).

Moderation при подаче жалобы (#18120) берёт current_version_id из GET /internal/events/{id}
или /internal/clubs/{id}, а текст на момент жалобы - из .../versions/{versionId}.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common import ApiError

from app.models import Club, ClubVersion, EventVersion
from app.repositories.events import EventRepository
from app.schemas.internal import ClubInternal, ClubVersionOut, EventInternal, EventVersionOut
from app.services.events import to_card


def _version_not_found() -> ApiError:
    return ApiError(404, "version_not_found", "Версия текста не найдена.")


async def get_event(session: AsyncSession, event_id: uuid.UUID) -> EventInternal:
    """Удалённое мероприятие недоступно, как и в публичном API."""
    row = await EventRepository(session).get(event_id)
    if row is None:
        raise ApiError(404, "event_not_found", "Мероприятие недоступно.")
    event, version = row
    # те же дата, место и цена, что в карточке каталога, без фото
    card = to_card(event, version).model_dump(exclude={"photo_url"})
    return EventInternal(
        **card,
        created_by_user_id=event.created_by_user_id,
        current_version_id=event.current_version_id,
    )


async def get_club(session: AsyncSession, club_id: uuid.UUID) -> ClubInternal:
    """Возвращает и заблокированную секцию: решает вызывающий сервис (OpenAPI)."""
    row = (
        await session.execute(
            select(Club, ClubVersion.name)
            .join(ClubVersion, ClubVersion.id == Club.current_version_id)
            .where(Club.id == club_id)
        )
    ).first()
    if row is None:
        raise ApiError(404, "club_not_found", "Секция недоступна.")
    club, name = row
    return ClubInternal(
        id=club.id, name=name, status=club.status, current_version_id=club.current_version_id
    )


async def get_event_version(
    session: AsyncSession, event_id: uuid.UUID, version_id: uuid.UUID
) -> EventVersionOut:
    """Версия отдаётся и для удалённого мероприятия: модератор смотрит текст на момент жалобы."""
    version = await session.scalar(
        select(EventVersion).where(EventVersion.id == version_id, EventVersion.event_id == event_id)
    )
    if version is None:
        raise _version_not_found()
    return EventVersionOut.model_validate(version, from_attributes=True)


async def get_club_version(
    session: AsyncSession, club_id: uuid.UUID, version_id: uuid.UUID
) -> ClubVersionOut:
    version = await session.scalar(
        select(ClubVersion).where(ClubVersion.id == version_id, ClubVersion.club_id == club_id)
    )
    if version is None:
        raise _version_not_found()
    return ClubVersionOut(
        id=version.id,
        club_id=version.club_id,
        version_no=version.version_no,
        name=version.name,
        description=version.description,
        meeting_place=version.meeting_place,
        schedule=version.schedule,
        contacts=version.contacts,
        # photo_url появится вместе с отдачей фото (#19424), как в GET /v1/clubs/{id}
        photo_url=None,
        edited_by=version.edited_by,
        created_at=version.created_at,
    )
