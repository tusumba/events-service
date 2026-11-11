import uuid
from decimal import Decimal
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import SCHEMA, Base, EventStatus, LifecycleStatus
from tests.events_factory import add_event, add_version


def _schema_diff(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection,
        opts={
            "include_schemas": True,
            "include_name": lambda name, type_, _: type_ != "schema" or name == SCHEMA,
            "compare_type": True,
            "version_table_schema": SCHEMA,
        },
    )
    return list(compare_metadata(context, Base.metadata))


@pytest.mark.usefixtures("migrated")
async def test_models_match_migrations(database_url: str) -> None:
    # Без search_path сервиса: иначе схема events считается схемой по умолчанию.
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        diff = await connection.run_sync(_schema_diff)
    await engine.dispose()
    assert diff == []


async def test_event_defaults(session: AsyncSession) -> None:
    event = await add_event(session)
    await session.refresh(event)
    assert event.status == EventStatus.CONFIRMED
    assert event.lifecycle_status == "active"
    assert event.created_at is not None


async def test_new_version_becomes_current(session: AsyncSession) -> None:
    event = await add_event(session, title="Старое название")
    version = await add_version(session, event, "Новое название")
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert event.current_version_id == version.id


async def test_current_version_must_belong_to_the_same_event(session: AsyncSession) -> None:
    first = await add_event(session)
    second = await add_event(session)
    with pytest.raises(IntegrityError, match="fk_events_id_current_version_id_event_versions"):
        async with session.begin_nested():
            first.current_version_id = second.current_version_id
            await session.flush()
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_current_version_must_exist(session: AsyncSession) -> None:
    event = await add_event(session)
    with pytest.raises(IntegrityError, match="fk_events_id_current_version_id_event_versions"):
        async with session.begin_nested():
            event.current_version_id = uuid.uuid4()
            await session.flush()
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.parametrize(
    ("is_free", "price"),
    [(True, Decimal("300.00")), (False, None), (False, Decimal("0"))],
)
async def test_price_matches_is_free(
    session: AsyncSession, is_free: bool, price: Decimal | None
) -> None:
    event = await add_event(session)
    with pytest.raises(IntegrityError, match="ck_events_price_matches_is_free"):
        async with session.begin_nested():
            event.is_free = is_free
            event.price = price
            await session.flush()


async def test_deleted_event_requires_deletion_details(session: AsyncSession) -> None:
    event = await add_event(session)
    with pytest.raises(IntegrityError, match="ck_events_deletion_matches_lifecycle"):
        async with session.begin_nested():
            event.lifecycle_status = LifecycleStatus.DELETED
            await session.flush()


async def test_version_numbers_are_unique_per_event(session: AsyncSession) -> None:
    event = await add_event(session)
    with pytest.raises(IntegrityError, match="uq_event_versions_event_id_version_no"):
        async with session.begin_nested():
            await session.execute(
                text(
                    "INSERT INTO event_versions (id, event_id, version_no, title, description,"
                    " edited_by) VALUES (:id, :event_id, 1, 'Дубль', '', :user)"
                ),
                {"id": uuid.uuid4(), "event_id": event.id, "user": uuid.uuid4()},
            )
