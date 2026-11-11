import uuid
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common.testing import generate_keypair, make_token

from app.models import EventStatus, TeamRole
from tests.events_factory import TODAY, add_event, add_member, add_version


@pytest.fixture
def private_key(monkeypatch: pytest.MonkeyPatch) -> str:
    private, public = generate_keypair()
    monkeypatch.setenv("JWT_PUBLIC_KEY", public)
    return private


def bearer(private_key: str, user_id: uuid.UUID | str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(private_key, user_id=str(user_id))}"}


async def test_page_of_paid_event(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    event = await add_event(
        session,
        title="Концерт",
        place_address="Новосибирск, ул. Пирогова, 2",
        price=Decimal("300.50"),
        status=EventStatus.NOT_CONFIRMED,
    )

    response = await client.get(f"/v1/events/{event.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(event.id),
        "title": "Концерт",
        "description": "Описание: Концерт",
        "date": str(TODAY),
        "place_address": "Новосибирск, ул. Пирогова, 2",
        "is_free": False,
        "price": {"amount": 30050, "currency": "RUB"},
        "status": "not_confirmed",
        "club_id": None,
        "photo_url": None,
        "organizer": {"type": "user", "user_id": str(event.created_by_user_id)},
        "current_version_id": str(event.current_version_id),
        "version_no": 1,
    }


async def test_free_event_has_no_price(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    event = await add_event(session)

    body = (await client.get(f"/v1/events/{event.id}")).json()

    assert body["is_free"] is True
    assert "price" not in body


async def test_club_is_organizer(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    club_id = uuid.uuid4()
    event = await add_event(session, club_id=club_id)

    body = (await client.get(f"/v1/events/{event.id}")).json()

    assert body["club_id"] == str(club_id)
    assert body["organizer"] == {"type": "club", "club_id": str(club_id)}


async def test_page_shows_current_version(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    event = await add_event(session, title="Старое название")
    version = await add_version(session, event, "Новое название")

    body = (await client.get(f"/v1/events/{event.id}")).json()

    assert body["title"] == "Новое название"
    assert body["description"] == "Описание: Новое название"
    assert body["current_version_id"] == str(version.id)
    assert body["version_no"] == 2


async def test_past_event_page_is_available(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    event = await add_event(session, date=TODAY.replace(year=2025), status=EventStatus.HELD)

    response = await client.get(f"/v1/events/{event.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "held"


async def test_unknown_event_is_not_found(client: httpx2.AsyncClient) -> None:
    response = await client.get(f"/v1/events/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "event_not_found",
        "message": "Мероприятие недоступно.",
    }


async def test_deleted_event_is_not_found(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    event = await add_event(session, deleted=True)

    response = await client.get(f"/v1/events/{event.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "event_not_found"


async def test_invalid_id_is_rejected(client: httpx2.AsyncClient) -> None:
    response = await client.get("/v1/events/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_team_member_sees_own_role(
    client: httpx2.AsyncClient, session: AsyncSession, private_key: str
) -> None:
    event = await add_event(session)
    user_id = await add_member(session, event, TeamRole.EDITOR)

    response = await client.get(f"/v1/events/{event.id}", headers=bearer(private_key, user_id))

    assert response.status_code == 200
    assert response.json()["my_role"] == "editor"


@pytest.mark.parametrize("user_id", [uuid.uuid4(), "not-a-uuid"])
async def test_user_outside_team_has_no_role(
    client: httpx2.AsyncClient, session: AsyncSession, private_key: str, user_id: uuid.UUID | str
) -> None:
    event = await add_event(session)
    await add_member(session, event, TeamRole.OWNER)

    response = await client.get(f"/v1/events/{event.id}", headers=bearer(private_key, user_id))

    assert response.status_code == 200
    assert "my_role" not in response.json()


async def test_role_in_another_event_is_not_shown(
    client: httpx2.AsyncClient, session: AsyncSession, private_key: str
) -> None:
    event = await add_event(session)
    other = await add_event(session)
    user_id = await add_member(session, other, TeamRole.OWNER)

    response = await client.get(f"/v1/events/{event.id}", headers=bearer(private_key, user_id))

    assert "my_role" not in response.json()


async def test_broken_token_is_rejected(
    client: httpx2.AsyncClient, session: AsyncSession, private_key: str
) -> None:
    event = await add_event(session)

    response = await client.get(
        f"/v1/events/{event.id}", headers={"Authorization": "Bearer broken"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"
