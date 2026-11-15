"""GET /internal/events/{id}/permissions: роль пользователя в команде мероприятия (#19039)."""

import uuid

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TeamRole
from tests.events_factory import add_event, add_member

SERVICE_TOKEN = "test-service-token"  # noqa: S105 - тестовое значение, не секрет
AUTH = {"X-Service-Token": SERVICE_TOKEN}


@pytest.fixture(autouse=True)
def service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)


async def permissions(
    client: httpx2.AsyncClient, event_id: uuid.UUID, user_id: uuid.UUID | str
) -> httpx2.Response:
    return await client.get(
        f"/internal/events/{event_id}/permissions", params={"user_id": str(user_id)}, headers=AUTH
    )


@pytest.mark.parametrize("role", list(TeamRole))
async def test_returns_role_of_team_member(
    client: httpx2.AsyncClient, session: AsyncSession, role: TeamRole
) -> None:
    event = await add_event(session)
    user_id = await add_member(session, event, role)

    response = await permissions(client, event.id, user_id)

    assert response.status_code == 200
    assert response.json() == {
        "event_id": str(event.id),
        "user_id": str(user_id),
        "is_member": True,
        "role": role.value,
    }


async def test_user_outside_team_is_not_member(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    event = await add_event(session)
    await add_member(session, event, TeamRole.OWNER)
    stranger = uuid.uuid4()

    response = await permissions(client, event.id, stranger)

    assert response.status_code == 200
    assert response.json() == {
        "event_id": str(event.id),
        "user_id": str(stranger),
        "is_member": False,
    }


async def test_role_is_per_event(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    first, second = await add_event(session), await add_event(session)
    user_id = await add_member(session, first, TeamRole.ADMIN)

    assert (await permissions(client, first.id, user_id)).json()["role"] == "admin"
    assert (await permissions(client, second.id, user_id)).json()["is_member"] is False


async def test_unknown_event_is_not_found(client: httpx2.AsyncClient) -> None:
    response = await permissions(client, uuid.uuid4(), uuid.uuid4())
    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "event_not_found",
        "message": "Мероприятие недоступно.",
    }


async def test_deleted_event_is_not_found(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    event = await add_event(session, deleted=True)
    user_id = await add_member(session, event, TeamRole.OWNER)
    assert (await permissions(client, event.id, user_id)).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}])
async def test_request_without_service_token_is_rejected(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    event = await add_event(session)
    response = await client.get(
        f"/internal/events/{event.id}/permissions",
        params={"user_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_user_jwt_is_not_enough(
    client: httpx2.AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tusumba_common.testing import generate_keypair, make_token

    private_key, public_key = generate_keypair()
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_key)
    event = await add_event(session)
    response = await client.get(
        f"/internal/events/{event.id}/permissions",
        params={"user_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {make_token(private_key)}"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize("params", [{}, {"user_id": "not-a-uuid"}])
async def test_user_id_is_required_uuid(
    client: httpx2.AsyncClient, session: AsyncSession, params: dict[str, str]
) -> None:
    event = await add_event(session)
    response = await client.get(
        f"/internal/events/{event.id}/permissions", params=params, headers=AUTH
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_invalid_event_id_is_validation_error(client: httpx2.AsyncClient) -> None:
    response = await client.get(
        "/internal/events/not-a-uuid/permissions",
        params={"user_id": str(uuid.uuid4())},
        headers=AUTH,
    )
    assert response.status_code == 422
