import uuid

from sqlalchemy import Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Club, ClubAdmin, ClubStatus, ClubVersion


def _current_versions_of_published_clubs() -> Select[ClubVersion]:
    return (
        select(ClubVersion)
        .join(Club, Club.current_version_id == ClubVersion.id)
        .where(Club.status == ClubStatus.PUBLISHED)
    )


async def list_published_clubs(
    session: AsyncSession, *, name_part: str | None, offset: int, limit: int
) -> tuple[list[ClubVersion], int]:
    statement = _current_versions_of_published_clubs()
    if name_part is not None:
        # autoescape: % и _ из запроса ищутся как обычные символы, а не как шаблон LIKE.
        statement = statement.where(
            func.lower(ClubVersion.name).contains(name_part.lower(), autoescape=True)
        )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    page = await session.scalars(
        statement.order_by(func.lower(ClubVersion.name), ClubVersion.club_id)
        .offset(offset)
        .limit(limit)
    )
    return list(page), total or 0


async def get_published_club(session: AsyncSession, club_id: uuid.UUID) -> ClubVersion | None:
    return await session.scalar(_current_versions_of_published_clubs().where(Club.id == club_id))


async def is_club_admin(session: AsyncSession, club_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    admin = exists().where(ClubAdmin.club_id == club_id, ClubAdmin.user_id == user_id)
    return bool(await session.scalar(select(admin)))
