import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer

from app.models import EventStatus


class Money(BaseModel):
    amount: int
    currency: Literal["RUB"] = "RUB"


class EventCard(BaseModel):
    id: uuid.UUID
    title: str
    date: dt.date
    place_address: str
    is_free: bool
    price: Money | None = None
    status: EventStatus
    club_id: uuid.UUID | None
    photo_url: str | None

    # В OpenAPI price необязательное, но не nullable: у бесплатного мероприятия поля нет.
    @model_serializer(mode="wrap")
    def _drop_empty_price(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if data.get("price") is None:
            data.pop("price", None)
        return data


class EventCardPage(BaseModel):
    items: list[EventCard]
    total: int
    page: int
    size: int
