"""Загрузка и удаление фото мероприятия и секции, выдача файла фото."""

import uuid

from fastapi import Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common import ApiError, CurrentUser

from app.models import Club, ClubStatus, ClubVersion, Event, LifecycleStatus, TeamRole
from app.photos import PHOTO_NOT_FOUND, PhotoStorage, media_type, new_photo_path, read_photo
from app.repositories.clubs import is_club_admin
from app.repositories.events import EventRepository

EVENT_EDITORS = frozenset({TeamRole.OWNER, TeamRole.ADMIN, TeamRole.EDITOR})

EVENT_NOT_FOUND = (404, "event_not_found", "Мероприятие недоступно.")
CLUB_NOT_FOUND = (404, "club_not_found", "Секция недоступна.")
EVENT_FORBIDDEN = (403, "forbidden", "У вас нет прав на редактирование мероприятия.")
CLUB_FORBIDDEN = (403, "forbidden", "У вас нет прав на редактирование секции.")


def _user_uuid(user: CurrentUser) -> uuid.UUID | None:
    try:
        return uuid.UUID(user.id)
    except ValueError:
        return None


async def _event_for_edit(session: AsyncSession, event_id: uuid.UUID, user: CurrentUser) -> Event:
    # FOR UPDATE: две загрузки подряд не потеряют файл, который заменила первая из них.
    event = await session.scalar(
        select(Event)
        .where(Event.id == event_id, Event.lifecycle_status == LifecycleStatus.ACTIVE)
        .with_for_update()
    )
    if event is None:
        raise ApiError(*EVENT_NOT_FOUND)
    user_id = _user_uuid(user)
    role = (
        None if user_id is None else await EventRepository(session).member_role(event_id, user_id)
    )
    if role not in EVENT_EDITORS:
        raise ApiError(*EVENT_FORBIDDEN)
    return event


async def _club_for_edit(
    session: AsyncSession, club_id: uuid.UUID, user: CurrentUser
) -> tuple[Club, ClubVersion, uuid.UUID]:
    club = await session.scalar(
        select(Club)
        .where(Club.id == club_id, Club.status == ClubStatus.PUBLISHED)
        .with_for_update()
    )
    if club is None:
        raise ApiError(*CLUB_NOT_FOUND)
    user_id = _user_uuid(user)
    if user_id is None or not await is_club_admin(session, club_id, user_id):
        raise ApiError(*CLUB_FORBIDDEN)
    current = await session.get_one(ClubVersion, club.current_version_id)
    return club, current, user_id


async def upload_event_photo(
    session: AsyncSession,
    storage: PhotoStorage,
    event_id: uuid.UUID,
    user: CurrentUser,
    file: UploadFile,
) -> str:
    """Заменяет фото мероприятия, прежний файл удаляется. Возвращает путь нового файла."""
    event = await _event_for_edit(session, event_id, user)
    content, extension = await read_photo(file)
    path = new_photo_path("events", event.id, extension)
    await storage.save(path, content)
    previous, event.photo_path = event.photo_path, path
    try:
        await session.commit()
    except BaseException:
        # База ссылку не сохранила - файл никому не нужен.
        await storage.delete(path)
        raise
    if previous is not None:
        await storage.delete(previous)
    return path


async def delete_event_photo(
    session: AsyncSession, storage: PhotoStorage, event_id: uuid.UUID, user: CurrentUser
) -> None:
    """Без фото клиент показывает стандартную обложку. Удалить уже удалённое - не ошибка."""
    event = await _event_for_edit(session, event_id, user)
    previous, event.photo_path = event.photo_path, None
    await session.commit()
    if previous is not None:
        await storage.delete(previous)


async def _new_club_version(
    session: AsyncSession,
    club: Club,
    current: ClubVersion,
    edited_by: uuid.UUID,
    photo_path: str | None,
) -> None:
    """Фото секции - часть страницы: новая версия копирует текущую и меняет только фото."""
    version = ClubVersion(
        id=uuid.uuid4(),
        club_id=club.id,
        version_no=current.version_no + 1,
        name=current.name,
        description=current.description,
        meeting_place=current.meeting_place,
        schedule=current.schedule,
        contacts=dict(current.contacts),
        photo_path=photo_path,
        edited_by=edited_by,
    )
    session.add(version)
    club.current_version_id = version.id
    await session.flush()


async def upload_club_photo(
    session: AsyncSession,
    storage: PhotoStorage,
    club_id: uuid.UUID,
    user: CurrentUser,
    file: UploadFile,
) -> str:
    """Новое фото создаёт новую версию страницы секции. Файлы прежних версий остаются:
    на версию может ссылаться жалоба."""
    club, current, user_id = await _club_for_edit(session, club_id, user)
    content, extension = await read_photo(file)
    path = new_photo_path("clubs", club.id, extension)
    await storage.save(path, content)
    try:
        await _new_club_version(session, club, current, user_id, path)
        await session.commit()
    except BaseException:
        await storage.delete(path)
        raise
    return path


async def delete_club_photo(session: AsyncSession, club_id: uuid.UUID, user: CurrentUser) -> None:
    club, current, user_id = await _club_for_edit(session, club_id, user)
    if current.photo_path is None:
        return
    await _new_club_version(session, club, current, user_id, None)
    await session.commit()


async def event_photo(
    session: AsyncSession, storage: PhotoStorage, event_id: uuid.UUID
) -> Response:
    path = await session.scalar(
        select(Event.photo_path).where(
            Event.id == event_id, Event.lifecycle_status == LifecycleStatus.ACTIVE
        )
    )
    return await _file_response(storage, path)


async def club_photo(session: AsyncSession, storage: PhotoStorage, club_id: uuid.UUID) -> Response:
    path = await session.scalar(
        select(ClubVersion.photo_path)
        .join(Club, Club.current_version_id == ClubVersion.id)
        .where(Club.id == club_id, Club.status == ClubStatus.PUBLISHED)
    )
    return await _file_response(storage, path)


async def _file_response(storage: PhotoStorage, path: str | None) -> Response:
    content = None if path is None else await storage.read(path)
    if path is None or content is None:
        raise ApiError(*PHOTO_NOT_FOUND)
    return Response(content, media_type=media_type(path))
