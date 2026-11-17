import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Club, ClubAdmin, ClubStatus, ClubVersion


async def add_club(
    session: AsyncSession,
    name: str,
    *,
    status: ClubStatus = ClubStatus.PUBLISHED,
    admins: tuple[uuid.UUID, ...] = (),
    **version_fields: Any,
) -> Club:
    club = Club(id=uuid.uuid4(), current_version_id=uuid.uuid4(), status=status)
    session.add(club)
    await session.flush()
    session.add(
        ClubVersion(
            id=club.current_version_id,
            club_id=club.id,
            version_no=1,
            name=name,
            description=version_fields.pop("description", f"Описание секции {name}"),
            edited_by=uuid.uuid4(),
            **version_fields,
        )
    )
    session.add_all(ClubAdmin(club_id=club.id, user_id=user_id) for user_id in admins)
    await session.flush()
    return club


async def add_version(
    session: AsyncSession, club: Club, name: str, **version_fields: Any
) -> ClubVersion:
    current = await session.get_one(ClubVersion, club.current_version_id)
    version = ClubVersion(
        id=uuid.uuid4(),
        club_id=club.id,
        version_no=current.version_no + 1,
        name=name,
        description=version_fields.pop("description", current.description),
        edited_by=uuid.uuid4(),
        **version_fields,
    )
    session.add(version)
    club.current_version_id = version.id
    await session.flush()
    return version
