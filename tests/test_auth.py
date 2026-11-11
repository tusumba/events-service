"""Проверка JWT, /internal и формата ошибок из tusumba-common. База для этих тестов не нужна."""

from collections.abc import AsyncIterator

import httpx2
import pytest
from tusumba_common.testing import generate_keypair, make_token

from app.main import create_app
from app.settings import Settings

SERVICE_TOKEN = "test-service-token"  # noqa: S105 - тестовое значение, не секрет


@pytest.fixture(scope="session")
def keypair() -> tuple[str, str]:
    return generate_keypair()


@pytest.fixture
def private_key(keypair: tuple[str, str]) -> str:
    return keypair[0]


@pytest.fixture
async def api(
    keypair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx2.AsyncClient]:
    monkeypatch.setenv("JWT_PUBLIC_KEY", keypair[1])
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)
    settings = Settings(database_url="postgresql+asyncpg://test:test@localhost:5432/test")
    transport = httpx2.ASGITransport(app=create_app(settings))
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_protected_endpoint_returns_current_user(
    api: httpx2.AsyncClient, private_key: str
) -> None:
    token = make_token(private_key, user_id="user-1", roles=["moderator"])
    response = await api.get("/v1/example/me", headers=bearer(token))
    assert response.status_code == 200
    assert response.json() == {"id": "user-1", "roles": ["moderator"]}


async def test_protected_endpoint_requires_token(api: httpx2.AsyncClient) -> None:
    response = await api.get("/v1/example/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("expires_in", "typ", "code"),
    [
        (-10, "access", "token_expired"),
        (3600, "refresh", "invalid_token"),
    ],
)
async def test_expired_and_refresh_tokens_are_rejected(
    api: httpx2.AsyncClient, private_key: str, expires_in: int, typ: str, code: str
) -> None:
    token = make_token(private_key, expires_in=expires_in, typ=typ)
    response = await api.get("/v1/example/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == code


async def test_token_signed_by_another_key_is_rejected(api: httpx2.AsyncClient) -> None:
    other_private_key, _ = generate_keypair()
    response = await api.get("/v1/example/me", headers=bearer(make_token(other_private_key)))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_optional_auth_allows_anonymous_and_rejects_broken_token(
    api: httpx2.AsyncClient,
) -> None:
    anonymous = await api.get("/v1/example/items")
    assert anonymous.status_code == 200
    assert anonymous.json() == {"items": [], "total": 0, "page": 1, "size": 20}

    broken = await api.get("/v1/example/items", headers=bearer("broken"))
    assert broken.status_code == 401
    assert broken.json()["error"]["code"] == "invalid_token"


async def test_validation_error_uses_common_format(api: httpx2.AsyncClient) -> None:
    response = await api.get("/v1/example/items", params={"size": 101})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Проверьте введённые данные."
    assert [detail["field"] for detail in error["details"]] == ["size"]


async def test_unknown_path_uses_common_format(api: httpx2.AsyncClient) -> None:
    response = await api.get("/v1/unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_internal_requires_service_token(api: httpx2.AsyncClient, private_key: str) -> None:
    for headers in ({}, {"X-Service-Token": "wrong"}, bearer(make_token(private_key))):
        response = await api.get("/internal/example/ping", headers=headers)
        assert response.status_code == 403, headers
        assert response.json()["error"]["code"] == "forbidden"

    response = await api.get("/internal/example/ping", headers={"X-Service-Token": SERVICE_TOKEN})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
