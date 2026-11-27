"""/internal для жалоб (#19428): мероприятие и секция с текущей версией, версия текста по id."""

import uuid
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClubStatus, EventStatus
from tests import clubs_factory
from tests.clubs_factory import add_club
from tests.events_factory import TODAY, add_event, add_version

SERVICE_TOKEN = "test-service-token"  # noqa: S105 - тестовое значение, не секрет
AUTH = {"X-Service-Token": SERVICE_TOKEN}


@pytest.fixture(autouse=True)
def service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)


async def get(client: httpx2.AsyncClient, path: str) -> httpx2.Response:
    return await client.get(path, headers=AUTH)


def assert_error(response: httpx2.Response, status: int, code: str, message: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"] == {"code": code, "message": message}


# GET /internal/events/{id}


async def test_event_with_current_version(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    club = await add_club(session, "Музклуб")
    event = await add_event(
        session,
        title="Концерт",
        price=Decimal("300.00"),
        status=EventStatus.NOT_CONFIRMED,
        club_id=club.id,
    )
    current = await add_version(session, event, "Концерт музклуба")

    response = await get(client, f"/internal/events/{event.id}")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": str(event.id),
        "title": "Концерт музклуба",
        "date": TODAY.isoformat(),
        "place_address": event.place_address,
        "is_free": False,
        "price": {"amount": 30000, "currency": "RUB"},
        "status": "not_confirmed",
        "club_id": str(club.id),
        "created_by_user_id": str(event.created_by_user_id),
        "current_version_id": str(current.id),
    }


async def test_free_event_has_no_price(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    event = await add_event(session)
    body = (await get(client, f"/internal/events/{event.id}")).json()
    assert body["is_free"] is True
    assert "price" not in body
    assert body["club_id"] is None


@pytest.mark.parametrize("deleted", [False, True])
async def test_unknown_or_deleted_event(
    client: httpx2.AsyncClient, session: AsyncSession, deleted: bool
) -> None:
    event_id = (await add_event(session, deleted=True)).id if deleted else uuid.uuid4()
    response = await get(client, f"/internal/events/{event_id}")
    assert_error(response, 404, "event_not_found", "Мероприятие недоступно.")


# GET /internal/events/{id}/versions/{versionId}


async def test_event_version_does_not_change_after_edit(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    """Текст на момент жалобы остаётся прежним после редактирования мероприятия (#18120)."""
    event = await add_event(session, title="Лекция о космосе")
    first_version_id = event.current_version_id
    await add_version(session, event, "Лекция о чёрных дырах")

    response = await get(client, f"/internal/events/{event.id}/versions/{first_version_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert {key: body[key] for key in ("id", "event_id", "version_no", "title", "description")} == {
        "id": str(first_version_id),
        "event_id": str(event.id),
        "version_no": 1,
        "title": "Лекция о космосе",
        "description": "Описание: Лекция о космосе",
    }
    assert body["edited_by"] == str(event.created_by_user_id)
    assert body["created_at"]


async def test_version_of_deleted_event_is_available(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    """Модератор смотрит текст жалобы и после удаления мероприятия."""
    event = await add_event(session, deleted=True)
    response = await get(client, f"/internal/events/{event.id}/versions/{event.current_version_id}")
    assert response.status_code == 200


async def test_event_version_of_other_event(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    first, second = await add_event(session), await add_event(session)
    for path in (
        f"/internal/events/{first.id}/versions/{second.current_version_id}",
        f"/internal/events/{first.id}/versions/{uuid.uuid4()}",
        f"/internal/events/{uuid.uuid4()}/versions/{first.current_version_id}",
    ):
        assert_error(await get(client, path), 404, "version_not_found", "Версия текста не найдена.")


# GET /internal/clubs/{id}


@pytest.mark.parametrize("status", list(ClubStatus))
async def test_club_with_current_version(
    client: httpx2.AsyncClient, session: AsyncSession, status: ClubStatus
) -> None:
    """Заблокированная секция тоже возвращается: решает вызывающий сервис."""
    club = await add_club(session, "Шахматы", status=status)
    current = await clubs_factory.add_version(session, club, "Шахматный клуб")

    response = await get(client, f"/internal/clubs/{club.id}")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": str(club.id),
        "name": "Шахматный клуб",
        "status": status.value,
        "current_version_id": str(current.id),
    }


async def test_unknown_club(client: httpx2.AsyncClient) -> None:
    response = await get(client, f"/internal/clubs/{uuid.uuid4()}")
    assert_error(response, 404, "club_not_found", "Секция недоступна.")


# GET /internal/clubs/{id}/versions/{versionId}


async def test_club_version_does_not_change_after_edit(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    club = await add_club(
        session,
        "Шахматы",
        meeting_place="ауд. 3107",
        schedule="Пятница, 18:00",
        contacts={"telegram": "@nsu_chess"},
    )
    first_version_id = club.current_version_id
    await clubs_factory.add_version(session, club, "Шахматный клуб", meeting_place="ауд. 4220")

    response = await get(client, f"/internal/clubs/{club.id}/versions/{first_version_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert {key: body[key] for key in body if key not in ("edited_by", "created_at")} == {
        "id": str(first_version_id),
        "club_id": str(club.id),
        "version_no": 1,
        "name": "Шахматы",
        "description": "Описание секции Шахматы",
        "meeting_place": "ауд. 3107",
        "schedule": "Пятница, 18:00",
        "contacts": {"telegram": "@nsu_chess"},
        "photo_url": None,
    }


async def test_version_of_blocked_club_is_available(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    club = await add_club(session, "Шахматы", status=ClubStatus.BLOCKED)
    response = await get(client, f"/internal/clubs/{club.id}/versions/{club.current_version_id}")
    assert response.status_code == 200


async def test_club_version_of_other_club(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    first, second = await add_club(session, "Шахматы"), await add_club(session, "Го")
    for path in (
        f"/internal/clubs/{first.id}/versions/{second.current_version_id}",
        f"/internal/clubs/{first.id}/versions/{uuid.uuid4()}",
    ):
        assert_error(await get(client, path), 404, "version_not_found", "Версия текста не найдена.")


# Сервисная авторизация


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}])
async def test_requires_service_token(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    event = await add_event(session)
    club = await add_club(session, "Шахматы")
    for path in (
        f"/internal/events/{event.id}",
        f"/internal/events/{event.id}/versions/{event.current_version_id}",
        f"/internal/clubs/{club.id}",
        f"/internal/clubs/{club.id}/versions/{club.current_version_id}",
    ):
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize(
    "path", ["/internal/events/not-a-uuid", "/internal/clubs/not-a-uuid/versions/also-not"]
)
async def test_ids_must_be_uuid(client: httpx2.AsyncClient, path: str) -> None:
    assert (await get(client, path)).status_code == 422
