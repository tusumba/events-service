from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tusumba_contracts import ApplicationApproved, Service, queue_name

from app.events import subscribe_event
from app.services.publication import handle_application_approved

APPLICATIONS_QUEUE = queue_name(Service.EVENTS, "applications")


def register_consumers(broker: RabbitBroker, sessions: async_sessionmaker[AsyncSession]) -> None:
    subscribe_event(
        broker,
        sessions,
        queue=APPLICATIONS_QUEUE,
        routing_key=ApplicationApproved.routing_key,
        handler=handle_application_approved,
    )
