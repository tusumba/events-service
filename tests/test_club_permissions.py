"""GET /internal/clubs/{id}/permissions: администратор ли пользователь секции (#19427)."""

import uuid

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClubStatus
from tests.clubs_factory import add_club

SERVICE_TOKEN = "test-service-token"  # noqa: S105 - тестовое значение, не секрет
AUTH = {"X-Service-Token": SERVICE_TOKEN}


@pytest.fixture(autouse=True)
def service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)


async def permissions(
    client: httpx2.AsyncClient,
    club_id: uuid.UUID,
    user_id: uuid.UUID | str,
    headers: dict[str, str] = AUTH,
) -> httpx2.Response:
    return await client.get(
        f"/internal/clubs/{club_id}/permissions", params={"user_id": str(user_id)}, headers=headers
    )


async def test_club_admin(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    admin = uuid.uuid4()
    club = await add_club(session, "Шахматы", admins=(admin,))

    response = await permissions(client, club.id, admin)

    assert response.status_code == 200
    assert response.json() == {"club_id": str(club.id), "user_id": str(admin), "is_admin": True}


async def test_user_is_not_admin(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    club = await add_club(session, "Шахматы", admins=(uuid.uuid4(),))
    stranger = uuid.uuid4()

    response = await permissions(client, club.id, stranger)

    assert response.status_code == 200
    assert response.json() == {"club_id": str(club.id), "user_id": str(stranger), "is_admin": False}


async def test_admin_rights_are_per_club(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    admin = uuid.uuid4()
    own = await add_club(session, "Шахматы", admins=(admin,))
    other = await add_club(session, "Го", admins=(uuid.uuid4(),))

    assert (await permissions(client, own.id, admin)).json()["is_admin"] is True
    assert (await permissions(client, other.id, admin)).json()["is_admin"] is False


@pytest.mark.parametrize("blocked", [False, True])
async def test_unknown_or_blocked_club_is_not_found(
    client: httpx2.AsyncClient, session: AsyncSession, blocked: bool
) -> None:
    admin = uuid.uuid4()
    club_id = uuid.uuid4()
    if blocked:
        club_id = (
            await add_club(session, "Шахматы", status=ClubStatus.BLOCKED, admins=(admin,))
        ).id

    response = await permissions(client, club_id, admin)

    assert response.status_code == 404
    assert response.json()["error"] == {"code": "club_not_found", "message": "Секция недоступна."}


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "wrong"}])
async def test_requires_service_token(
    client: httpx2.AsyncClient, session: AsyncSession, headers: dict[str, str]
) -> None:
    club = await add_club(session, "Шахматы")

    response = await permissions(client, club.id, uuid.uuid4(), headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_user_id_must_be_uuid(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    club = await add_club(session, "Шахматы")
    response = await permissions(client, club.id, "not-a-uuid")
    assert response.status_code == 422
