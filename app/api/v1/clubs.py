import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from tusumba_common import ApiError, CurrentUser, optional_user

from app.db import Session
from app.models import ClubVersion
from app.repositories.clubs import get_published_club, is_club_admin, list_published_clubs

router = APIRouter(prefix="/clubs", tags=["clubs"])

OptionalUser = Annotated[CurrentUser | None, Depends(optional_user)]


class ClubCard(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    photo_url: str | None


class ClubCardPage(BaseModel):
    items: list[ClubCard]
    total: int
    page: int
    size: int


class ClubDetail(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    meeting_place: str | None
    schedule: str | None
    contacts: dict[str, str]
    photo_url: str | None
    current_version_id: uuid.UUID
    version_no: int
    is_admin: bool


def club_not_found() -> ApiError:
    return ApiError(404, "club_not_found", "Секция недоступна.")


def photo_url(version: ClubVersion) -> str | None:
    return f"/v1/clubs/{version.club_id}/photo" if version.photo_path else None


def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


@router.get("")
async def list_clubs(
    db: Session,
    _user: OptionalUser,
    query: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ClubCardPage:
    versions, total = await list_published_clubs(
        db, name_part=query, offset=(page - 1) * size, limit=size
    )
    items = [
        ClubCard(
            id=version.club_id,
            name=version.name,
            description=version.description,
            photo_url=photo_url(version),
        )
        for version in versions
    ]
    return ClubCardPage(items=items, total=total, page=page, size=size)


@router.get("/{id}")
async def get_club(
    id: Annotated[str, Path(json_schema_extra={"format": "uuid"})],
    db: Session,
    user: OptionalUser,
) -> ClubDetail:
    # id не UUID - такой секции нет: тот же 404, что и для несуществующей, а не 422.
    club_id = parse_uuid(id)
    version = await get_published_club(db, club_id) if club_id else None
    if version is None:
        raise club_not_found()
    user_id = parse_uuid(user.id) if user else None
    return ClubDetail(
        id=version.club_id,
        name=version.name,
        description=version.description,
        meeting_place=version.meeting_place,
        schedule=version.schedule,
        contacts=version.contacts,
        photo_url=photo_url(version),
        current_version_id=version.id,
        version_no=version.version_no,
        is_admin=user_id is not None and await is_club_admin(db, version.club_id, user_id),
    )
