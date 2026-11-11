import uuid
from typing import Any

import httpx2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common.testing import generate_keypair, make_token

from app.models import ClubStatus
from tests.clubs_factory import add_club, add_version


@pytest.fixture(scope="session")
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def private_key(keypair: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("JWT_PUBLIC_KEY", keypair[1])
    return keypair[0]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def catalog(client: httpx2.AsyncClient, **params: Any) -> dict[str, Any]:
    response = await client.get("/v1/clubs", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def names(page: dict[str, Any]) -> list[str]:
    return [item["name"] for item in page["items"]]


async def test_catalog_shows_only_published_clubs_sorted_by_name(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await add_club(session, "Бета")
    await add_club(session, "альфа")
    await add_club(session, "Гамма", status=ClubStatus.BLOCKED)

    assert names(await catalog(client)) == ["альфа", "Бета"]


async def test_catalog_card_fields(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    with_photo = await add_club(
        session, "Фотоклуб", description="Снимаем город", photo_path="clubs/1.jpg"
    )
    without_photo = await add_club(session, "Шахматы", description="Играем по средам")

    page = await catalog(client)

    assert page["items"] == [
        {
            "id": str(with_photo.id),
            "name": "Фотоклуб",
            "description": "Снимаем город",
            "photo_url": f"/v1/clubs/{with_photo.id}/photo",
        },
        {
            "id": str(without_photo.id),
            "name": "Шахматы",
            "description": "Играем по средам",
            "photo_url": None,
        },
    ]


async def test_catalog_paginates(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    for name in ("А", "Б", "В"):
        await add_club(session, name)

    first = await catalog(client, page=1, size=2)
    second = await catalog(client, page=2, size=2)

    assert (names(first), first["total"], first["page"], first["size"]) == (["А", "Б"], 3, 1, 2)
    assert (names(second), second["total"], second["page"], second["size"]) == (["В"], 3, 2, 2)


async def test_empty_catalog_returns_empty_page(client: httpx2.AsyncClient) -> None:
    assert await catalog(client) == {"items": [], "total": 0, "page": 1, "size": 20}


async def test_search_finds_part_of_name_ignoring_case(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await add_club(session, "Настольные игры")
    await add_club(session, "Шахматы")
    await add_club(session, "Настольный теннис", status=ClubStatus.BLOCKED)

    page = await catalog(client, query="СТОЛЬН")

    assert names(page) == ["Настольные игры"]
    assert page["total"] == 1


async def test_search_looks_at_current_version_only(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    club = await add_club(session, "Футбол")
    await add_version(session, club, "Баскетбол")

    assert names(await catalog(client, query="футб")) == []
    assert names(await catalog(client, query="баскет")) == ["Баскетбол"]


async def test_search_without_matches_returns_empty_page(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    await add_club(session, "Шахматы")

    assert await catalog(client, query="хоккей") == {
        "items": [],
        "total": 0,
        "page": 1,
        "size": 20,
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [("%", ["100% спорт"]), ("_", ["Клуб_программистов"]), ("0%_", [])],
)
async def test_search_treats_like_wildcards_literally(
    client: httpx2.AsyncClient, session: AsyncSession, query: str, expected: list[str]
) -> None:
    for name in ("100% спорт", "Клуб_программистов", "Шахматы"):
        await add_club(session, name)

    assert names(await catalog(client, query=query)) == expected


async def test_club_page_shows_current_version(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    club = await add_club(session, "Хор", meeting_place="Актовый зал")
    current = await add_version(
        session,
        club,
        "Хор НГУ",
        description="Поём классику",
        meeting_place="Ауд. 101",
        schedule="Вторник, 19:00",
        contacts={"telegram": "@nsu_choir"},
        photo_path="clubs/choir.jpg",
    )

    response = await client.get(f"/v1/clubs/{club.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(club.id),
        "name": "Хор НГУ",
        "description": "Поём классику",
        "meeting_place": "Ауд. 101",
        "schedule": "Вторник, 19:00",
        "contacts": {"telegram": "@nsu_choir"},
        "photo_url": f"/v1/clubs/{club.id}/photo",
        "current_version_id": str(current.id),
        "version_no": 2,
        "is_admin": False,
    }


async def test_club_page_without_optional_fields(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    club = await add_club(session, "Шахматы")

    body = (await client.get(f"/v1/clubs/{club.id}")).json()

    assert (body["meeting_place"], body["schedule"], body["contacts"], body["photo_url"]) == (
        None,
        None,
        {},
        None,
    )


@pytest.mark.parametrize(("is_club_admin", "expected"), [(True, True), (False, False)])
async def test_club_page_shows_whether_user_is_admin(
    client: httpx2.AsyncClient,
    session: AsyncSession,
    private_key: str,
    is_club_admin: bool,
    expected: bool,
) -> None:
    admin_id, other_user_id = uuid.uuid4(), uuid.uuid4()
    club = await add_club(session, "Шахматы", admins=(admin_id,))
    user_id = admin_id if is_club_admin else other_user_id

    response = await client.get(
        f"/v1/clubs/{club.id}", headers=bearer(make_token(private_key, user_id=str(user_id)))
    )

    assert response.status_code == 200
    assert response.json()["is_admin"] is expected


async def test_admin_of_another_club_is_not_admin(
    client: httpx2.AsyncClient, session: AsyncSession, private_key: str
) -> None:
    user_id = uuid.uuid4()
    await add_club(session, "Шахматы", admins=(user_id,))
    club = await add_club(session, "Шашки")

    response = await client.get(
        f"/v1/clubs/{club.id}", headers=bearer(make_token(private_key, user_id=str(user_id)))
    )

    assert response.json()["is_admin"] is False


async def test_user_id_that_is_not_uuid_is_not_admin(
    client: httpx2.AsyncClient, session: AsyncSession, private_key: str
) -> None:
    club = await add_club(session, "Шахматы")

    response = await client.get(
        f"/v1/clubs/{club.id}", headers=bearer(make_token(private_key, user_id="1"))
    )

    assert response.status_code == 200
    assert response.json()["is_admin"] is False


@pytest.mark.parametrize("kind", ["blocked", "missing", "not_uuid"])
async def test_blocked_missing_and_malformed_ids_look_the_same(
    client: httpx2.AsyncClient, session: AsyncSession, kind: str
) -> None:
    club_ids = {
        "blocked": str((await add_club(session, "Шахматы", status=ClubStatus.BLOCKED)).id),
        "missing": str(uuid.uuid4()),
        "not_uuid": "not-a-uuid",
    }

    response = await client.get(f"/v1/clubs/{club_ids[kind]}")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "club_not_found", "message": "Секция недоступна."}}


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"query": ""}, "query"),
        ({"query": "а" * 101}, "query"),
        ({"page": 0}, "page"),
        ({"page": "first"}, "page"),
        ({"size": 0}, "size"),
        ({"size": 101}, "size"),
    ],
)
async def test_invalid_catalog_parameters_return_validation_error(
    client: httpx2.AsyncClient, params: dict[str, Any], field: str
) -> None:
    response = await client.get("/v1/clubs", params=params)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [detail["field"] for detail in error["details"]] == [field]


async def test_query_of_max_length_is_accepted(client: httpx2.AsyncClient) -> None:
    assert (await catalog(client, query="а" * 100))["items"] == []


@pytest.mark.parametrize("path", ["/v1/clubs", f"/v1/clubs/{uuid.uuid4()}"])
@pytest.mark.parametrize(
    ("expired", "code"),
    [(False, "invalid_token"), (True, "token_expired")],
    ids=["broken", "expired"],
)
async def test_invalid_token_returns_401(
    client: httpx2.AsyncClient, private_key: str, path: str, expired: bool, code: str
) -> None:
    token = make_token(private_key, expires_in=-10) if expired else "broken"

    response = await client.get(path, headers=bearer(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == code
