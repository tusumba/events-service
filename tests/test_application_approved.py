import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any, cast

import httpx2
import pytest
from fastapi import FastAPI
from faststream.rabbit import RabbitBroker
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tusumba_common.testing import generate_keypair, make_token
from tusumba_contracts import (
    ApplicationApproved,
    BaseEvent,
    ClubPageApplicationData,
    EventApplicationData,
    EventEnvelope,
    EventPublished,
    Money,
)

from app.consumers import register_consumers
from app.db import create_engine, create_sessionmaker
from app.events import EVENT_EXCHANGE, process_event
from app.models import (
    Club,
    ClubAdmin,
    ClubStatus,
    ClubVersion,
    Event,
    EventTeamMember,
    EventVersion,
    OutboxMessage,
    ProcessedEvent,
    TeamRole,
)
from app.services.events import today_in_novosibirsk
from app.services.publication import handle_application_approved
from app.settings import Settings
from tests.clubs_factory import add_club
from tests.events_factory import TODAY


def approved(**overrides: Any) -> EventEnvelope[ApplicationApproved]:
    fields: dict[str, Any] = {
        "application_id": uuid.uuid4(),
        "type": "event",
        "author_user_id": uuid.uuid4(),
        "club_id": None,
        "result_object_id": uuid.uuid4(),
        "event": EventApplicationData(
            title="Посвят ФИТ",
            description="Концерт, конкурсы и дискотека",
            date=TODAY + dt.timedelta(days=7),
            place_address="Новосибирск, ул. Пирогова, 2",
            is_free=False,
            price=Money(amount=30000),
        ),
        "processed_by": uuid.uuid4(),
        "processed_at": dt.datetime(2026, 11, 11, 8, 0, tzinfo=dt.UTC),
    } | overrides
    return ApplicationApproved(**fields).envelope()


async def handle(session: AsyncSession, envelope: EventEnvelope[ApplicationApproved]) -> None:
    # Обработчик принимает EventEnvelope[BaseEvent], как его передаёт process_event.
    await handle_application_approved(session, cast(EventEnvelope[BaseEvent], envelope))


def message(envelope: EventEnvelope[ApplicationApproved]) -> dict[str, Any]:
    return envelope.model_dump(mode="json")


@pytest.fixture
async def sessions(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    # Транзакции process_event - точки сохранения внутри транзакции теста, она откатится.
    connection = await session.connection()
    return async_sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )


async def published_for(session: AsyncSession, event_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(OutboxMessage.payload).where(
            OutboxMessage.routing_key == EventPublished.routing_key,
            OutboxMessage.payload["payload"]["event_id"].astext == str(event_id),
        )
    )
    return list(rows)


async def events_with_id(session: AsyncSession, event_id: uuid.UUID) -> int:
    return await session.scalar(select(func.count()).where(Event.id == event_id)) or 0


async def test_event_is_created_with_first_version_and_owner(session: AsyncSession) -> None:
    envelope = approved()
    payload = envelope.payload

    await handle(session, envelope)

    event = await session.get(Event, payload.result_object_id)
    assert event is not None
    assert event.created_by_user_id == payload.author_user_id
    assert event.date == TODAY + dt.timedelta(days=7)
    assert event.place_address == "Новосибирск, ул. Пирогова, 2"
    assert (event.is_free, event.price) == (False, Decimal("300.00"))
    version = await session.get(EventVersion, event.current_version_id)
    assert version is not None
    assert (version.event_id, version.version_no) == (event.id, 1)
    assert (version.title, version.description) == ("Посвят ФИТ", "Концерт, конкурсы и дискотека")
    assert version.edited_by == payload.author_user_id
    owner = await session.get(EventTeamMember, (event.id, payload.author_user_id))
    assert owner is not None
    assert owner.role == TeamRole.OWNER


async def test_event_published_goes_to_outbox(session: AsyncSession) -> None:
    envelope = approved()
    payload = envelope.payload

    await handle(session, envelope)

    event = await session.get(Event, payload.result_object_id)
    assert event is not None
    [published] = await published_for(session, event.id)
    assert published["event_type"] == "EventPublished"
    assert published["producer"] == "events"
    assert published["payload"] == {
        "event_id": str(event.id),
        "current_version_id": str(event.current_version_id),
        "title": "Посвят ФИТ",
        "date": str(TODAY + dt.timedelta(days=7)),
        "place_address": "Новосибирск, ул. Пирогова, 2",
        "is_free": False,
        "price": {"amount": 30000, "currency": "RUB"},
        "status": "confirmed",
        "club_id": None,
        "created_by_user_id": str(payload.author_user_id),
    }


async def test_free_event_from_club(session: AsyncSession) -> None:
    club_id = (await add_club(session, "Шахматы")).id
    data = EventApplicationData(
        title="Турнир", description="Шахматы", date=TODAY, place_address="НГУ", is_free=True
    )
    envelope = approved(club_id=club_id, event=data)

    await handle(session, envelope)

    event = await session.get(Event, envelope.payload.result_object_id)
    assert event is not None
    assert (event.is_free, event.price, event.club_id) == (True, None, club_id)
    [published] = await published_for(session, event.id)
    assert published["payload"]["price"] is None
    assert published["payload"]["club_id"] == str(club_id)


async def test_repeated_delivery_does_not_create_second_event(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    envelope = approved()
    event_id = envelope.payload.result_object_id

    assert await process_event(sessions, message(envelope), handle_application_approved) is True
    assert await process_event(sessions, message(envelope), handle_application_approved) is False

    assert await events_with_id(session, event_id) == 1
    assert len(await published_for(session, event_id)) == 1
    assert await session.get(ProcessedEvent, envelope.event_id) is not None


async def test_new_message_for_existing_event_is_ignored(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    first = approved()
    again = approved(
        application_id=first.payload.application_id,
        result_object_id=first.payload.result_object_id,
    )
    assert again.event_id != first.event_id

    await process_event(sessions, message(first), handle_application_approved)
    await process_event(sessions, message(again), handle_application_approved)

    assert await events_with_id(session, first.payload.result_object_id) == 1
    assert len(await published_for(session, first.payload.result_object_id)) == 1


def club_approved(**overrides: Any) -> EventEnvelope[ApplicationApproved]:
    club_page = ClubPageApplicationData(
        name="Шахматный клуб",
        description="Играем по средам",
        meeting_place="Ауд. 3107",
        schedule="Среда, 18:00",
        contacts={"telegram": "@nsu_chess"},
    )
    return approved(type="club_page", event=None, club_page=club_page, **overrides)


async def club_rows(session: AsyncSession, club_id: uuid.UUID) -> tuple[int, int, int]:
    clubs = await session.scalar(select(func.count()).where(Club.id == club_id))
    versions = await session.scalar(select(func.count()).where(ClubVersion.club_id == club_id))
    admins = await session.scalar(select(func.count()).where(ClubAdmin.club_id == club_id))
    return clubs or 0, versions or 0, admins or 0


async def test_club_is_created_with_first_version_and_admin(session: AsyncSession) -> None:
    envelope = club_approved()
    payload = envelope.payload

    await handle(session, envelope)

    club = await session.get(Club, payload.result_object_id)
    assert club is not None
    assert club.status == ClubStatus.PUBLISHED
    version = await session.get(ClubVersion, club.current_version_id)
    assert version is not None
    assert (version.club_id, version.version_no) == (club.id, 1)
    assert (version.name, version.description) == ("Шахматный клуб", "Играем по средам")
    assert (version.meeting_place, version.schedule) == ("Ауд. 3107", "Среда, 18:00")
    assert version.contacts == {"telegram": "@nsu_chess"}
    assert version.photo_path is None
    assert version.edited_by == payload.author_user_id
    assert await session.get(ClubAdmin, (payload.author_user_id, club.id)) is not None
    assert await events_with_id(session, payload.result_object_id) == 0
    assert await published_for(session, payload.result_object_id) == []


async def test_club_without_optional_fields(session: AsyncSession) -> None:
    club_page = ClubPageApplicationData(name="Хор", description="Поём классику")
    envelope = approved(type="club_page", event=None, club_page=club_page)

    await handle(session, envelope)

    club = await session.get(Club, envelope.payload.result_object_id)
    assert club is not None
    version = await session.get(ClubVersion, club.current_version_id)
    assert version is not None
    assert (version.meeting_place, version.schedule, version.contacts) == (None, None, {})


async def test_repeated_delivery_does_not_create_second_club(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    envelope = club_approved()

    assert await process_event(sessions, message(envelope), handle_application_approved) is True
    assert await process_event(sessions, message(envelope), handle_application_approved) is False

    assert await club_rows(session, envelope.payload.result_object_id) == (1, 1, 1)


async def test_new_message_for_existing_club_is_ignored(
    session: AsyncSession, sessions: async_sessionmaker[AsyncSession]
) -> None:
    first = club_approved()
    again = club_approved(
        application_id=first.payload.application_id,
        author_user_id=first.payload.author_user_id,
        result_object_id=first.payload.result_object_id,
    )
    assert again.event_id != first.event_id

    assert await process_event(sessions, message(first), handle_application_approved) is True
    assert await process_event(sessions, message(again), handle_application_approved) is True

    assert await club_rows(session, first.payload.result_object_id) == (1, 1, 1)


async def test_created_club_appears_in_catalog_and_author_is_admin(
    client: httpx2.AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key, public_key = generate_keypair()
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_key)
    envelope = club_approved()
    payload = envelope.payload

    await process_event(sessions, message(envelope), handle_application_approved)

    [card] = (await client.get("/v1/clubs")).json()["items"]
    assert (card["id"], card["name"]) == (str(payload.result_object_id), "Шахматный клуб")
    token = make_token(private_key, user_id=str(payload.author_user_id))
    page = await client.get(
        f"/v1/clubs/{payload.result_object_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert page.status_code == 200
    assert page.json()["is_admin"] is True


async def test_created_event_appears_in_catalog(
    app: FastAPI,
    client: httpx2.AsyncClient,
    session: AsyncSession,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    app.dependency_overrides[today_in_novosibirsk] = lambda: TODAY
    envelope = approved()

    await process_event(sessions, message(envelope), handle_application_approved)

    [card] = (await client.get("/v1/events")).json()["items"]
    assert card["id"] == str(envelope.payload.result_object_id)
    assert card["title"] == "Посвят ФИТ"
    assert card["price"] == {"amount": 30000, "currency": "RUB"}
    assert card["status"] == "confirmed"


@pytest.fixture
async def committed_sessions(settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(settings)
    yield create_sessionmaker(engine)
    await engine.dispose()


async def cleanup(
    sessions: async_sessionmaker[AsyncSession], envelope: EventEnvelope[ApplicationApproved]
) -> None:
    event_id = envelope.payload.result_object_id
    async with sessions.begin() as session:
        await session.execute(delete(EventTeamMember).where(EventTeamMember.event_id == event_id))
        await session.execute(delete(EventVersion).where(EventVersion.event_id == event_id))
        await session.execute(delete(Event).where(Event.id == event_id))
        await session.execute(
            delete(OutboxMessage).where(
                OutboxMessage.payload["payload"]["event_id"].astext == str(event_id)
            )
        )
        await session.execute(
            delete(ProcessedEvent).where(ProcessedEvent.event_id == envelope.event_id)
        )


async def test_message_from_rabbitmq_creates_event_once(
    committed_sessions: async_sessionmaker[AsyncSession], rabbitmq_url: str
) -> None:
    envelope = approved()
    event_id = envelope.payload.result_object_id
    broker = RabbitBroker(rabbitmq_url)
    register_consumers(broker, committed_sessions)

    async def processed() -> None:
        while True:
            async with committed_sessions() as session:
                if await session.get(ProcessedEvent, envelope.event_id) is not None:
                    return
            await asyncio.sleep(0.05)

    await broker.start()
    try:
        for _ in range(2):
            await broker.publish(
                message(envelope),
                exchange=EVENT_EXCHANGE,
                routing_key=ApplicationApproved.routing_key,
                persist=True,
                message_id=str(envelope.event_id),
            )
        await asyncio.wait_for(processed(), timeout=10)
        await asyncio.sleep(0.3)

        async with committed_sessions() as session:
            assert await events_with_id(session, event_id) == 1
            owner = await session.get(EventTeamMember, (event_id, envelope.payload.author_user_id))
            assert owner is not None
            assert owner.role == TeamRole.OWNER
            assert len(await published_for(session, event_id)) == 1
    finally:
        await broker.stop()
        await cleanup(committed_sessions, envelope)
