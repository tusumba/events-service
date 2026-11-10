"""Пример публичного роутера на tusumba-common. При создании сервиса замените своими роутерами."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from tusumba_common import CurrentUser, get_current_user, optional_user

router = APIRouter(prefix="/example", tags=["example"])


class Me(BaseModel):
    id: str
    roles: list[str]


class ItemPage(BaseModel):
    items: list[str]
    total: int
    page: int
    size: int


@router.get("/me")
async def example_me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> Me:
    return Me(id=user.id, roles=user.roles)


@router.get("/items")
async def example_items(
    _user: Annotated[CurrentUser | None, Depends(optional_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ItemPage:
    return ItemPage(items=[], total=0, page=page, size=size)
