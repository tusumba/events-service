import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response, UploadFile, status
from pydantic import BaseModel
from tusumba_common import CurrentUser, get_current_user

from app.db import Session
from app.photos import Photos, photo_url
from app.services import photos

router = APIRouter(tags=["photos"])

User = Annotated[CurrentUser, Depends(get_current_user)]
EventId = Annotated[uuid.UUID, Path(alias="id")]
ClubId = Annotated[uuid.UUID, Path(alias="id")]

PHOTO_FILE: dict[int | str, dict[str, Any]] = {
    status.HTTP_200_OK: {
        "content": {media: {} for media in ("image/jpeg", "image/png", "image/webp")},
        "description": "Файл фото",
    }
}


class Photo(BaseModel):
    photo_url: str


@router.get(
    "/events/{id}/photo",
    operation_id="getEventPhoto",
    summary="Фото мероприятия",
    response_class=Response,
    responses=PHOTO_FILE,
)
async def get_event_photo(session: Session, storage: Photos, event_id: EventId) -> Response:
    return await photos.event_photo(session, storage, event_id)


@router.put(
    "/events/{id}/photo", operation_id="uploadEventPhoto", summary="Загрузить фото мероприятия"
)
async def upload_event_photo(
    session: Session, storage: Photos, user: User, event_id: EventId, file: UploadFile
) -> Photo:
    path = await photos.upload_event_photo(session, storage, event_id, user, file)
    return Photo(photo_url=photo_url("events", event_id, path))


@router.delete(
    "/events/{id}/photo",
    operation_id="deleteEventPhoto",
    summary="Удалить фото мероприятия",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_event_photo(
    session: Session, storage: Photos, user: User, event_id: EventId
) -> None:
    await photos.delete_event_photo(session, storage, event_id, user)


@router.get(
    "/clubs/{id}/photo",
    operation_id="getClubPhoto",
    summary="Фото секции",
    response_class=Response,
    responses=PHOTO_FILE,
)
async def get_club_photo(session: Session, storage: Photos, club_id: ClubId) -> Response:
    return await photos.club_photo(session, storage, club_id)


@router.put("/clubs/{id}/photo", operation_id="uploadClubPhoto", summary="Загрузить фото секции")
async def upload_club_photo(
    session: Session, storage: Photos, user: User, club_id: ClubId, file: UploadFile
) -> Photo:
    path = await photos.upload_club_photo(session, storage, club_id, user, file)
    return Photo(photo_url=photo_url("clubs", club_id, path))


@router.delete(
    "/clubs/{id}/photo",
    operation_id="deleteClubPhoto",
    summary="Удалить фото секции",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_club_photo(session: Session, user: User, club_id: ClubId) -> None:
    await photos.delete_club_photo(session, club_id, user)
