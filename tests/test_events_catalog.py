import datetime as dt
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common.testing import generate_keypair, make_token

from app.models import EventStatus
from app.services.events import today_in_novosibirsk
from tests.events_factory import TODAY, add_event, add_version

DAY = dt.timedelta(days=1)


@pytest.fixture
async def api(app: FastAPI, client: httpx2.AsyncClient) -> AsyncIterator[httpx2.AsyncClient]:
    app.dependency_overrides[today_in_novosibirsk] = lambda: TODAY
    yield client


def titles(response: httpx2.Response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


async def test_empty_catalog_returns_empty_list(api: httpx2.AsyncClient) -> None:
    response = await api.get("/v1/events")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_card_of_paid_event(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    club_id = uuid.uuid4()
    event = await add_event(
        session,
        title="Концерт",
        date=TODAY + DAY,
        place_address="Новосибирск, ул. Пирогова, 2",
        price=Decimal("300.50"),
        status=EventStatus.NOT_CONFIRMED,
        club_id=club_id,
    )

    response = await api.get("/v1/events")

    assert response.json()["items"] == [
        {
            "id": str(event.id),
            "title": "Концерт",
            "date": "2026-11-12",
            "place_address": "Новосибирск, ул. Пирогова, 2",
            "is_free": False,
            "price": {"amount": 30050, "currency": "RUB"},
            "status": "not_confirmed",
            "club_id": str(club_id),
            "photo_url": None,
        }
    ]


async def test_free_event_card_has_no_price(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session)
    [card] = (await api.get("/v1/events")).json()["items"]
    assert card["is_free"] is True
    assert "price" not in card
    assert card["club_id"] is None


async def test_nearest_events_come_first(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session, title="Через неделю", date=TODAY + 7 * DAY)
    await add_event(session, title="Сегодня", date=TODAY)
    await add_event(session, title="Через месяц", date=TODAY + 30 * DAY)
    await add_event(session, title="Завтра", date=TODAY + DAY)

    response = await api.get("/v1/events")

    assert titles(response) == ["Сегодня", "Завтра", "Через неделю", "Через месяц"]


async def test_anonymous_and_signed_in_users_see_catalog(
    api: httpx2.AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_key)
    await add_event(session, title="Лекция")
    token = make_token(private_key)

    anonymous = await api.get("/v1/events")
    signed_in = await api.get("/v1/events", headers={"Authorization": f"Bearer {token}"})

    assert titles(anonymous) == titles(signed_in) == ["Лекция"]


async def test_events_on_the_same_date_keep_stable_order(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    events = [await add_event(session, title=f"Мероприятие {n}") for n in range(5)]
    expected = [str(event.id) for event in sorted(events, key=lambda event: event.id)]

    first = await api.get("/v1/events", params={"size": 2})
    rest = await api.get("/v1/events", params={"size": 2, "page": 2})
    last = await api.get("/v1/events", params={"size": 2, "page": 3})

    ids = [item["id"] for page in (first, rest, last) for item in page.json()["items"]]
    assert ids == expected


async def test_past_and_deleted_events_are_hidden(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await add_event(session, title="Вчера", date=TODAY - DAY)
    await add_event(session, title="Удалено", date=TODAY + DAY, deleted=True)
    await add_event(session, title="Завтра", date=TODAY + DAY)

    response = await api.get("/v1/events")

    assert titles(response) == ["Завтра"]
    assert response.json()["total"] == 1


async def test_events_of_every_status_are_shown(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    for status in EventStatus:
        await add_event(session, status=status)

    response = await api.get("/v1/events")

    assert {item["status"] for item in response.json()["items"]} == set(EventStatus)


async def test_card_shows_title_of_current_version(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    event = await add_event(session, title="Старое название")
    await add_version(session, event, "Новое название")

    assert titles(await api.get("/v1/events")) == ["Новое название"]


async def test_pagination(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    for day in range(5):
        await add_event(session, title=f"День {day}", date=TODAY + day * DAY)

    first = await api.get("/v1/events", params={"page": 1, "size": 2})
    second = await api.get("/v1/events", params={"page": 2, "size": 2})
    third = await api.get("/v1/events", params={"page": 3, "size": 2})

    assert titles(first) == ["День 0", "День 1"]
    assert titles(second) == ["День 2", "День 3"]
    assert titles(third) == ["День 4"]
    assert {key: second.json()[key] for key in ("total", "page", "size")} == {
        "total": 5,
        "page": 2,
        "size": 2,
    }


async def test_page_after_the_last_is_empty(api: httpx2.AsyncClient, session: AsyncSession) -> None:
    await add_event(session)

    response = await api.get("/v1/events", params={"page": 3, "size": 20})

    assert response.json() == {"items": [], "total": 1, "page": 3, "size": 20}


async def test_default_and_maximum_page_size(
    api: httpx2.AsyncClient, session: AsyncSession
) -> None:
    for _ in range(101):
        await add_event(session)

    default = await api.get("/v1/events")
    maximum = await api.get("/v1/events", params={"size": 100})

    assert len(default.json()["items"]) == 20
    assert len(maximum.json()["items"]) == 100
    assert maximum.json()["total"] == 101


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"page": 0}, "page"),
        ({"page": "first"}, "page"),
        ({"size": 0}, "size"),
        ({"size": 101}, "size"),
    ],
)
async def test_invalid_pagination_is_rejected(
    api: httpx2.AsyncClient, params: dict[str, int | str], field: str
) -> None:
    response = await api.get("/v1/events", params=params)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [detail["field"] for detail in error["details"]] == [field]


async def test_broken_token_is_rejected(
    api: httpx2.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_PUBLIC_KEY", generate_keypair()[1])
    response = await api.get("/v1/events", headers={"Authorization": "Bearer broken"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
