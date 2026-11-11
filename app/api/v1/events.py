import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from tusumba_common import CurrentUser, optional_user

from app.db import Session
from app.schemas.events import EventCardPage
from app.services import events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", operation_id="listEvents", summary="Каталог мероприятий")
async def list_events(
    session: Session,
    _user: Annotated[CurrentUser | None, Depends(optional_user)],
    today: Annotated[dt.date, Depends(events.today_in_novosibirsk)],
    page: Annotated[int, Query(ge=1, description="Номер страницы, с 1")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 20,
) -> EventCardPage:
    return await events.list_events(session, today, page, size)
