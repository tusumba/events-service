import asyncio
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import SCHEMA, Club, ClubStatus, ClubVersion
from tests.clubs_factory import add_club

CLUB_TABLES = {"clubs", "club_versions", "club_admins"}
CLUB_ENUMS = {"club_status"}

async def club_objects(database_url: str) -> tuple[set[str], set[str]]:
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        tables = await connection.scalars(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"),
            {"s": SCHEMA},
        )
        types = await connection.scalars(
            text(
                "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = :s AND t.typtype = 'e'"
            ),
            {"s": SCHEMA},
        )
        result = set(tables) & CLUB_TABLES, set(types) & CLUB_ENUMS
    await engine.dispose()
    return result


@pytest.mark.usefixtures("migrated")
async def test_downgrade_removes_club_schema_and_upgrade_restores_it(
    alembic_config: Config, database_url: str
) -> None:
    try:
        await asyncio.to_thread(command.downgrade, alembic_config, "base")
        assert await club_objects(database_url) == (set(), set())
    finally:
        await asyncio.to_thread(command.upgrade, alembic_config, "head")
    assert await club_objects(database_url) == (CLUB_TABLES, CLUB_ENUMS)


async def test_club_and_first_version_are_created_in_one_transaction(
    session: AsyncSession,
) -> None:
    await add_club(session, "Шахматы")

    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_club_must_point_to_existing_version(session: AsyncSession) -> None:
    session.add(Club(current_version_id=uuid.uuid4(), status=ClubStatus.PUBLISHED))
    await session.flush()

    with pytest.raises(IntegrityError):
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_version_numbers_are_unique_within_club(session: AsyncSession) -> None:
    club = await add_club(session, "Шахматы")
    session.add(
        ClubVersion(
            club_id=club.id, version_no=1, name="Шахматы", description="", edited_by=uuid.uuid4()
        )
    )

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_name_search_can_use_trigram_index(session: AsyncSession) -> None:
    await add_club(session, "Шахматы")
    await session.execute(text("SET LOCAL enable_seqscan = off"))

    plan = await session.scalars(
        text("EXPLAIN SELECT id FROM club_versions WHERE lower(name) LIKE :p ESCAPE '/'"),
        {"p": "%хмат%"},
    )

    assert "ix_club_versions_lower_name_trgm" in "\n".join(plan)
