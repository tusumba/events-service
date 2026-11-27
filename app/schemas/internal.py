"""Ответы /internal для других сервисов (OpenAPI Events: EventInternal, ClubInternal, версии)."""

import datetime as dt
import uuid
from typing import ClassVar

from pydantic import BaseModel

from app.models import ClubStatus, EventStatus
from app.schemas.events import Money, OmitEmptyModel


class EventInternal(OmitEmptyModel):
    """Мероприятие с текущей версией текста: по current_version_id Moderation фиксирует жалобу."""

    omit_if_none: ClassVar[tuple[str, ...]] = ("price",)

    id: uuid.UUID
    title: str
    date: dt.date
    place_address: str
    is_free: bool
    price: Money | None = None
    status: EventStatus
    club_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    current_version_id: uuid.UUID


class ClubInternal(BaseModel):
    id: uuid.UUID
    name: str
    status: ClubStatus
    current_version_id: uuid.UUID


class EventVersionOut(BaseModel):
    """Версия текста мероприятия (EventVersion в OpenAPI). Строки версий не изменяются."""

    id: uuid.UUID
    event_id: uuid.UUID
    version_no: int
    title: str
    description: str
    edited_by: uuid.UUID
    created_at: dt.datetime


class ClubVersionOut(BaseModel):
    """Версия страницы секции (ClubVersion в OpenAPI)."""

    id: uuid.UUID
    club_id: uuid.UUID
    version_no: int
    name: str
    description: str
    meeting_place: str | None
    schedule: str | None
    contacts: dict[str, str]
    photo_url: str | None
    edited_by: uuid.UUID
    created_at: dt.datetime
