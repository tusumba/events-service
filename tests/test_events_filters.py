import datetime as dt
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EventStatus
from app.services.events import today_in_novosibirsk
from tests.events_factory import TODAY, add_event

DAY = dt.timedelta(days=1)


@pytest.fixture
async def api(app: FastAPI, client: httpx2.AsyncClient) -> AsyncIterator[httpx2.AsyncClient]:
    app.dependency_overrides[today_in_novosibirsk] = lambda: TODAY
    yield client


async def titles(api: httpx2.AsyncClient, **params: Any) -> list[str]:
    response = await api.get("/v1/events", params=params)
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


async def test_filter_by_type(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session, title="Бесплатное")
    await add_event(session, title="Платное", price=Decimal("500"))

    assert await titles(api, is_free="true") == ["Бесплатное"]
    assert await titles(api, is_free="false") == ["Платное"]
    assert sorted(await titles(api)) == ["Бесплатное", "Платное"]


async def test_filter_by_date_range(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    for day in range(5):
        await add_event(session, title=f"День {day}", date=TODAY + day * DAY)

    assert await titles(api, date_from=str(TODAY + 3 * DAY)) == ["День 3", "День 4"]
    assert await titles(api, date_to=str(TODAY + DAY)) == ["День 0", "День 1"]
    assert await titles(api, date_from=str(TODAY + DAY), date_to=str(TODAY + 2 * DAY)) == [
        "День 1",
        "День 2",
    ]
    assert await titles(api, date_from=str(TODAY + 2 * DAY), date_to=str(TODAY + 2 * DAY)) == [
        "День 2"
    ]


async def test_date_from_shows_past_events(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session, title="Неделю назад", date=TODAY - 7 * DAY)
    await add_event(session, title="Сегодня")

    assert await titles(api) == ["Сегодня"]
    assert await titles(api, date_from=str(TODAY - 7 * DAY)) == ["Неделю назад", "Сегодня"]


async def test_date_to_before_date_from_returns_empty_list(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await add_event(session, date=TODAY + DAY)

    response = await api.get(
        "/v1/events", params={"date_from": str(TODAY + 2 * DAY), "date_to": str(TODAY)}
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_filter_by_place(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session, title="НГУ", place_address="Новосибирск, ул. Пирогова, 1")
    await add_event(session, title="Академпарк", place_address="Новосибирск, ул. Николаева, 11")

    assert await titles(api, place="пирогова") == ["НГУ"]
    assert await titles(api, place="ПИРОГОВА") == ["НГУ"]
    assert sorted(await titles(api, place="Новосибирск")) == ["Академпарк", "НГУ"]
    assert await titles(api, place="Бердск") == []


async def test_place_wildcards_are_literal(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session, title="Скидка", place_address="Корпус 100% готов")
    await add_event(session, title="Подчёркивание", place_address="Ауд_31")
    await add_event(session, title="Другое", place_address="Аудитория 31")

    assert await titles(api, place="%") == ["Скидка"]
    assert await titles(api, place="_") == ["Подчёркивание"]


async def test_filter_by_one_status(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    for status in EventStatus:
        await add_event(session, title=status.value, status=status)

    assert await titles(api, status="held") == ["held"]


async def test_filter_by_several_statuses(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    for status in EventStatus:
        await add_event(session, title=status.value, status=status)

    response = await api.get("/v1/events", params=[("status", "held"), ("status", "not_held")])

    assert response.status_code == 200
    assert sorted(item["status"] for item in response.json()["items"]) == ["held", "not_held"]


async def test_filters_are_combined(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(
        session,
        title="Подходит",
        date=TODAY + DAY,
        place_address="Новосибирск, ул. Пирогова, 1",
        price=Decimal("300"),
        status=EventStatus.CONFIRMED,
    )
    await add_event(
        session,
        title="Бесплатное",
        date=TODAY + DAY,
        place_address="Новосибирск, ул. Пирогова, 1",
        status=EventStatus.CONFIRMED,
    )
    await add_event(
        session,
        title="Другое место",
        date=TODAY + DAY,
        place_address="Бердск",
        price=Decimal("300"),
        status=EventStatus.CONFIRMED,
    )
    await add_event(
        session,
        title="Другой статус",
        date=TODAY + DAY,
        place_address="Новосибирск, ул. Пирогова, 1",
        price=Decimal("300"),
        status=EventStatus.NOT_CONFIRMED,
    )
    await add_event(
        session,
        title="Позже",
        date=TODAY + 10 * DAY,
        place_address="Новосибирск, ул. Пирогова, 1",
        price=Decimal("300"),
        status=EventStatus.CONFIRMED,
    )

    assert await titles(
        api,
        is_free="false",
        date_to=str(TODAY + 2 * DAY),
        place="Пирогова",
        status="confirmed",
    ) == ["Подходит"]


async def test_no_matches_returns_empty_list(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await add_event(session, place_address="Новосибирск", status=EventStatus.CONFIRMED)

    response = await api.get("/v1/events", params={"place": "Новосибирск", "status": "held"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_filters_work_with_pagination(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    for day in range(5):
        await add_event(session, title=f"Платное {day}", date=TODAY + day * DAY, price=Decimal(1))
        await add_event(session, title=f"Бесплатное {day}", date=TODAY + day * DAY)

    response = await api.get("/v1/events", params={"is_free": "false", "page": 2, "size": 2})

    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Платное 2", "Платное 3"]
    assert (body["total"], body["page"], body["size"]) == (5, 2, 2)


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"is_free": "maybe"}, "is_free"),
        ({"date_from": "11.11.2026"}, "date_from"),
        ({"date_to": "2026-13-01"}, "date_to"),
        ({"place": ""}, "place"),
        ({"place": "а" * 201}, "place"),
        ({"status": "cancelled"}, "status.0"),
    ],
)
async def test_invalid_filters_are_rejected(
    api: httpx2.AsyncClient, params: dict[str, str], field: str
) -> None:
    response = await api.get("/v1/events", params=params)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [detail["field"] for detail in error["details"]] == [field]
