import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common import ApiError

from app.models import Event, EventTeamMember, LifecycleStatus
from app.schemas.permissions import EventPermissions


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
