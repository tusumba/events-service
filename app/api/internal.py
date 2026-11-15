"""Пути /internal для других сервисов: только с верным X-Service-Token, иначе 403."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from tusumba_common import require_service

from app.api.health import Health
from app.db import Session
from app.schemas.permissions import EventPermissions
from app.services import permissions

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
