import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from tusumba_common import CurrentUser, optional_user

from app.db import Session
from app.models import EventStatus
from app.repositories.events import EventFilters
from app.schemas.events import EventCardPage, EventDetail
from app.services import events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", operation_id="listEvents", summary="Каталог мероприятий")
async def list_events(
    session: Session,
    _user: Annotated[CurrentUser | None, Depends(optional_user)],
    today: Annotated[dt.date, Depends(events.today_in_novosibirsk)],
    is_free: Annotated[
        bool | None, Query(description="Тип мероприятия - true бесплатные, false платные")
    ] = None,
    date_from: Annotated[
        dt.date | None, Query(description="Мероприятия не раньше этой даты, по умолчанию сегодня")
    ] = None,
    date_to: Annotated[dt.date | None, Query(description="Мероприятия не позже этой даты")] = None,
    place: Annotated[
        str | None,
        Query(min_length=1, max_length=200, description="Часть адреса места проведения"),
    ] = None,
    status: Annotated[
        list[EventStatus] | None,
        Query(description="Статусы подтверждения, можно указать несколько"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Номер страницы, с 1")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 20,
) -> EventCardPage:
    filters = EventFilters(
        date_from=date_from or today,
        date_to=date_to,
        is_free=is_free,
        place=place,
        statuses=status or (),
    )
    return await events.list_events(session, filters, page, size)


@router.get("/{id}", operation_id="getEvent", summary="Страница мероприятия")
async def get_event(
    session: Session,
    user: Annotated[CurrentUser | None, Depends(optional_user)],
    event_id: Annotated[uuid.UUID, Path(alias="id")],
) -> EventDetail:
    return await events.get_event(session, event_id, user)
