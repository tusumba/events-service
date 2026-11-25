import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common import ApiError

from app.models import Club, ClubStatus, Event, EventTeamMember, LifecycleStatus
from app.repositories.clubs import is_club_admin
from app.schemas.permissions import ClubPermissions, EventPermissions


async def event_permissions(
    session: AsyncSession, event_id: uuid.UUID, user_id: uuid.UUID
) -> EventPermissions:
    exists = await session.scalar(
        select(Event.id).where(
            Event.id == event_id, Event.lifecycle_status == LifecycleStatus.ACTIVE
        )
    )
    if exists is None:
        raise ApiError(404, "event_not_found", "Мероприятие недоступно.")
    role = await session.scalar(
        select(EventTeamMember.role).where(
            EventTeamMember.event_id == event_id, EventTeamMember.user_id == user_id
        )
    )
    return EventPermissions(
        event_id=event_id, user_id=user_id, is_member=role is not None, role=role
    )


async def club_permissions(
    session: AsyncSession, club_id: uuid.UUID, user_id: uuid.UUID
) -> ClubPermissions:
    """Заблокированная секция недоступна так же, как несуществующая (OpenAPI, ClubNotFound)."""
    exists = await session.scalar(
        select(Club.id).where(Club.id == club_id, Club.status == ClubStatus.PUBLISHED)
    )
    if exists is None:
        raise ApiError(404, "club_not_found", "Секция недоступна.")
    return ClubPermissions(
        club_id=club_id, user_id=user_id, is_admin=await is_club_admin(session, club_id, user_id)
    )
