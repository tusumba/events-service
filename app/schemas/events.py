import datetime as dt
import uuid
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, SerializerFunctionWrapHandler, model_serializer

from app.models import EventStatus, TeamRole


class OmitEmptyModel(BaseModel):
    """Поля из omit_if_none в OpenAPI необязательные, но не nullable: при None их нет в ответе."""

    omit_if_none: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for name in self.omit_if_none:
            if data.get(name) is None:
                data.pop(name, None)
        return data


class Money(BaseModel):
    amount: int
    currency: Literal["RUB"] = "RUB"


class EventCard(OmitEmptyModel):
    omit_if_none: ClassVar[tuple[str, ...]] = ("price",)

    id: uuid.UUID
    title: str
    date: dt.date
    place_address: str
    is_free: bool
    price: Money | None = None
    status: EventStatus
    club_id: uuid.UUID | None
    photo_url: str | None


class EventCardPage(BaseModel):
    items: list[EventCard]
    total: int
    page: int
    size: int


class Organizer(OmitEmptyModel):
    omit_if_none: ClassVar[tuple[str, ...]] = ("user_id", "club_id", "club_name")

    type: Literal["user", "club"]
    user_id: uuid.UUID | None = None
    club_id: uuid.UUID | None = None
    club_name: str | None = None


class EventDetail(EventCard):
    omit_if_none: ClassVar[tuple[str, ...]] = ("price", "my_role")

    description: str
    organizer: Organizer
    current_version_id: uuid.UUID
    version_no: int
    my_role: TeamRole | None = None
