from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from app.db import create_engine, get_session
from app.main import create_app
from app.settings import Settings

SERVICE_DIR = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config(SERVICE_DIR / "alembic.ini")
    config.set_main_option("script_location", str(SERVICE_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def migrated(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")


@pytest.fixture
def settings(database_url: str, migrated: None) -> Settings:
    return Settings(
        service_name="events",
        environment="test",
        database_url=database_url,
    )


@pytest.fixture
async def session(settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = create_engine(settings)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as db_session:
            yield db_session
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI, session: AsyncSession) -> AsyncIterator[httpx2.AsyncClient]:
    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
