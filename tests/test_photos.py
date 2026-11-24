"""Фото мероприятий и секций: загрузка, проверка файла, права, удаление (#19424, #18098, #18103)."""

import uuid
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tusumba_common.testing import generate_keypair, make_token

from app.models import ClubStatus, ClubVersion, Event, TeamRole
from app.photos import MAX_SIZE, DiskPhotoStorage, get_photo_storage
from tests.clubs_factory import add_club
from tests.events_factory import TODAY, add_event, add_member

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


@pytest.fixture(scope="session")
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def private_key(keypair: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("JWT_PUBLIC_KEY", keypair[1])
    return keypair[0]


@pytest.fixture
def photos_dir(app: FastAPI, tmp_path: Path) -> Path:
    storage = DiskPhotoStorage(tmp_path)
    app.dependency_overrides[get_photo_storage] = lambda: storage
    return tmp_path


def bearer(private_key: str, user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(private_key, user_id=str(user_id))}"}


def stored_files(photos_dir: Path) -> list[Path]:
    return sorted(path for path in photos_dir.rglob("*") if path.is_file())


async def upload(
    client: httpx2.AsyncClient,
    url: str,
    headers: dict[str, str],
    content: bytes = PNG,
    content_type: str = "image/png",
) -> httpx2.Response:
    return await client.put(url, files={"file": ("photo", content, content_type)}, headers=headers)


async def page(client: httpx2.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.mark.parametrize("role", [TeamRole.OWNER, TeamRole.ADMIN, TeamRole.EDITOR])
async def test_event_team_uploads_photo(
    client: httpx2.AsyncClient,
    session: AsyncSession,
    photos_dir: Path,
    private_key: str,
    role: TeamRole,
) -> None:
    event = await add_event(session)
    user_id = await add_member(session, event, role)

    response = await upload(client, f"/v1/events/{event.id}/photo", bearer(private_key, user_id))

    assert response.status_code == 200, response.text
    photo_url = response.json()["photo_url"]
    assert photo_url.startswith(f"/v1/events/{event.id}/photo?v=")
    assert (await page(client, f"/v1/events/{event.id}"))["photo_url"] == photo_url
    [card] = (await page(client, f"/v1/events?date_from={TODAY}"))["items"]
    assert card["photo_url"] == photo_url
    photo = await client.get(photo_url)
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"
    assert photo.content == PNG


@pytest.mark.parametrize(
    ("content", "media_type"), [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")]
)
async def test_type_is_taken_from_file_content(
    client: httpx2.AsyncClient,
    session: AsyncSession,
    photos_dir: Path,
    private_key: str,
    content: bytes,
    media_type: str,
) -> None:
    event = await add_event(session)
    owner = await add_member(session, event, TeamRole.OWNER)

    response = await upload(
        client,
        f"/v1/events/{event.id}/photo",
        bearer(private_key, owner),
        content,
        "application/octet-stream",
    )

    photo = await client.get(response.json()["photo_url"])
    assert photo.headers["content-type"] == media_type


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"%PDF-1.7 " + b"\x00" * 64, "image/png"),
        (b"GIF89a" + b"\x00" * 64, "image/gif"),
        (b"", "image/png"),
        (PNG + b"\x00" * MAX_SIZE, "image/png"),
    ],
    ids=["pdf-named-png", "gif", "empty", "over-5mb"],
)
async def test_unsuitable_file_is_rejected(
    client: httpx2.AsyncClient,
    session: AsyncSession,
    photos_dir: Path,
    private_key: str,
    content: bytes,
    content_type: str,
) -> None:
    event = await add_event(session)
    owner = await add_member(session, event, TeamRole.OWNER)

    response = await upload(
        client, f"/v1/events/{event.id}/photo", bearer(private_key, owner), content, content_type
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "file_invalid",
        "message": "Файл не соответствует требованиям.",
    }
    assert stored_files(photos_dir) == []


async def test_photo_of_exactly_5_mb_is_accepted(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    event = await add_event(session)
    owner = await add_member(session, event, TeamRole.OWNER)
    content = PNG + b"\x00" * (MAX_SIZE - len(PNG))

    response = await upload(
        client, f"/v1/events/{event.id}/photo", bearer(private_key, owner), content
    )

    assert response.status_code == 200


async def test_missing_file_is_validation_error(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    event = await add_event(session)
    owner = await add_member(session, event, TeamRole.OWNER)

    response = await client.put(
        f"/v1/events/{event.id}/photo", data={"other": "x"}, headers=bearer(private_key, owner)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("role", [TeamRole.SCANNER, None])
async def test_others_cannot_change_event_photo(
    client: httpx2.AsyncClient,
    session: AsyncSession,
    photos_dir: Path,
    private_key: str,
    role: TeamRole | None,
) -> None:
    event = await add_event(session)
    user_id = uuid.uuid4() if role is None else await add_member(session, event, role)
    headers = bearer(private_key, user_id)

    uploaded = await upload(client, f"/v1/events/{event.id}/photo", headers)
    deleted = await client.delete(f"/v1/events/{event.id}/photo", headers=headers)

    for response in (uploaded, deleted):
        assert response.status_code == 403
        assert response.json()["error"] == {
            "code": "forbidden",
            "message": "У вас нет прав на редактирование мероприятия.",
        }
    assert stored_files(photos_dir) == []


async def test_upload_requires_token(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path
) -> None:
    event = await add_event(session)

    uploaded = await upload(client, f"/v1/events/{event.id}/photo", {})
    deleted = await client.delete(f"/v1/events/{event.id}/photo")

    assert (uploaded.status_code, deleted.status_code) == (401, 401)


async def test_unknown_or_deleted_event_is_not_found(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    deleted = await add_event(session, deleted=True)
    owner = await add_member(session, deleted, TeamRole.OWNER)

    for event_id in (deleted.id, uuid.uuid4()):
        response = await upload(client, f"/v1/events/{event_id}/photo", bearer(private_key, owner))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "event_not_found"


async def test_new_photo_replaces_previous_file(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    event = await add_event(session)
    headers = bearer(private_key, await add_member(session, event, TeamRole.OWNER))

    first = (await upload(client, f"/v1/events/{event.id}/photo", headers)).json()["photo_url"]
    second = (await upload(client, f"/v1/events/{event.id}/photo", headers, JPEG)).json()[
        "photo_url"
    ]

    assert first != second
    [file] = stored_files(photos_dir)
    assert file.read_bytes() == JPEG
    assert (await client.get(f"/v1/events/{event.id}/photo")).content == JPEG


async def test_deleted_event_photo_falls_back_to_default_cover(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    event = await add_event(session)
    headers = bearer(private_key, await add_member(session, event, TeamRole.EDITOR))
    await upload(client, f"/v1/events/{event.id}/photo", headers)

    response = await client.delete(f"/v1/events/{event.id}/photo", headers=headers)
    again = await client.delete(f"/v1/events/{event.id}/photo", headers=headers)

    assert (response.status_code, again.status_code) == (204, 204)
    assert (await page(client, f"/v1/events/{event.id}"))["photo_url"] is None
    assert await session.scalar(select(Event.photo_path).where(Event.id == event.id)) is None
    assert stored_files(photos_dir) == []
    photo = await client.get(f"/v1/events/{event.id}/photo")
    assert photo.status_code == 404
    assert photo.json()["error"] == {"code": "photo_not_found", "message": "Фото не найдено."}


async def test_event_without_photo(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path
) -> None:
    event = await add_event(session)

    assert (await page(client, f"/v1/events/{event.id}"))["photo_url"] is None
    for event_id in (event.id, uuid.uuid4()):
        response = await client.get(f"/v1/events/{event_id}/photo")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "photo_not_found"


async def test_club_admin_uploads_photo_as_new_version(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    admin = uuid.uuid4()
    club = await add_club(
        session,
        "Фотоклуб",
        admins=(admin,),
        meeting_place="ауд. 101",
        schedule="по средам",
        contacts={"telegram": "@photo"},
    )
    first_version_id = club.current_version_id

    response = await upload(client, f"/v1/clubs/{club.id}/photo", bearer(private_key, admin), WEBP)

    assert response.status_code == 200, response.text
    photo_url = response.json()["photo_url"]
    assert photo_url.startswith(f"/v1/clubs/{club.id}/photo?v=")
    body = await page(client, f"/v1/clubs/{club.id}")
    assert (body["photo_url"], body["version_no"]) == (photo_url, 2)
    assert (body["name"], body["meeting_place"], body["schedule"], body["contacts"]) == (
        "Фотоклуб",
        "ауд. 101",
        "по средам",
        {"telegram": "@photo"},
    )
    version = await session.get_one(ClubVersion, uuid.UUID(body["current_version_id"]))
    assert version.edited_by == admin
    assert (await session.get_one(ClubVersion, first_version_id)).photo_path is None
    [card] = (await page(client, "/v1/clubs"))["items"]
    assert card["photo_url"] == photo_url
    photo = await client.get(photo_url)
    assert (photo.headers["content-type"], photo.content) == ("image/webp", WEBP)


async def test_deleted_club_photo_keeps_file_of_old_version(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    admin = uuid.uuid4()
    club = await add_club(session, "Фотоклуб", admins=(admin,))
    headers = bearer(private_key, admin)
    await upload(client, f"/v1/clubs/{club.id}/photo", headers)

    response = await client.delete(f"/v1/clubs/{club.id}/photo", headers=headers)
    again = await client.delete(f"/v1/clubs/{club.id}/photo", headers=headers)

    assert (response.status_code, again.status_code) == (204, 204)
    body = await page(client, f"/v1/clubs/{club.id}")
    assert (body["photo_url"], body["version_no"]) == (None, 3)
    paths = await session.scalars(
        select(ClubVersion.photo_path)
        .where(ClubVersion.club_id == club.id)
        .order_by(ClubVersion.version_no)
    )
    assert [path is not None for path in paths] == [False, True, False]
    assert len(stored_files(photos_dir)) == 1
    assert (await client.get(f"/v1/clubs/{club.id}/photo")).status_code == 404


async def test_only_club_admin_changes_club_photo(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    club = await add_club(session, "Шахматы", admins=(uuid.uuid4(),))
    headers = bearer(private_key, uuid.uuid4())

    uploaded = await upload(client, f"/v1/clubs/{club.id}/photo", headers)
    deleted = await client.delete(f"/v1/clubs/{club.id}/photo", headers=headers)

    for response in (uploaded, deleted):
        assert response.status_code == 403
        assert response.json()["error"] == {
            "code": "forbidden",
            "message": "У вас нет прав на редактирование секции.",
        }
    assert (await page(client, f"/v1/clubs/{club.id}"))["version_no"] == 1
    assert stored_files(photos_dir) == []


async def test_blocked_or_unknown_club_is_not_found(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    admin = uuid.uuid4()
    blocked = await add_club(session, "Закрытая", status=ClubStatus.BLOCKED, admins=(admin,))

    for club_id in (blocked.id, uuid.uuid4()):
        response = await upload(client, f"/v1/clubs/{club_id}/photo", bearer(private_key, admin))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "club_not_found"
        assert (await client.get(f"/v1/clubs/{club_id}/photo")).status_code == 404


async def test_club_photo_file_is_checked(
    client: httpx2.AsyncClient, session: AsyncSession, photos_dir: Path, private_key: str
) -> None:
    admin = uuid.uuid4()
    club = await add_club(session, "Шахматы", admins=(admin,))

    response = await upload(
        client, f"/v1/clubs/{club.id}/photo", bearer(private_key, admin), b"not an image"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "file_invalid"
    assert (await page(client, f"/v1/clubs/{club.id}"))["version_no"] == 1
