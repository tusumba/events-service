"""Пути /internal для других сервисов: только с верным X-Service-Token, иначе 403."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from tusumba_common import require_service

from app.api.health import Health
from app.db import Session
from app.schemas.internal import ClubInternal, ClubVersionOut, EventInternal, EventVersionOut
from app.schemas.permissions import EventPermissions
from app.services import internal, permissions

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_service)])


@router.get("/example/ping")
async def example_ping() -> Health:
    return Health()


@router.get(
    "/events/{id}/permissions",
    operation_id="getEventPermissions",
    summary="Роль пользователя в команде мероприятия",
    response_model_exclude_none=True,
)
async def get_event_permissions(
    session: Session,
    event_id: Annotated[uuid.UUID, Path(alias="id")],
    user_id: Annotated[uuid.UUID, Query(description="Пользователь, права которого проверяются")],
) -> EventPermissions:
    """Ticketing и Moderation проверяют роль и кешируют ответ на 30-60 секунд (tusumba-common)."""
    return await permissions.event_permissions(session, event_id, user_id)


EventIdPath = Annotated[uuid.UUID, Path(alias="id")]
ClubIdPath = Annotated[uuid.UUID, Path(alias="id")]
VersionIdPath = Annotated[uuid.UUID, Path(alias="versionId")]


@router.get(
    "/events/{id}",
    operation_id="getEventInternal",
    summary="Мероприятие для других сервисов",
)
async def get_event(session: Session, event_id: EventIdPath) -> EventInternal:
    """Ticketing - дата, статус и цена; Moderation - текущая версия текста при жалобе (#18120)."""
    return await internal.get_event(session, event_id)


@router.get(
    "/events/{id}/versions/{versionId}",
    operation_id="getEventVersionInternal",
    summary="Версия текста мероприятия",
)
async def get_event_version(
    session: Session, event_id: EventIdPath, version_id: VersionIdPath
) -> EventVersionOut:
    """Moderation получает текст на момент жалобы."""
    return await internal.get_event_version(session, event_id, version_id)


@router.get("/clubs/{id}", operation_id="getClubInternal", summary="Секция для других сервисов")
async def get_club(session: Session, club_id: ClubIdPath) -> ClubInternal:
    """Moderation проверяет секцию и получает текущую версию страницы при жалобе."""
    return await internal.get_club(session, club_id)


@router.get(
    "/clubs/{id}/versions/{versionId}",
    operation_id="getClubVersionInternal",
    summary="Версия страницы секции",
)
async def get_club_version(
    session: Session, club_id: ClubIdPath, version_id: VersionIdPath
) -> ClubVersionOut:
    """Moderation получает текст страницы секции на момент жалобы."""
    return await internal.get_club_version(session, club_id, version_id)
