import uuid

from pydantic import BaseModel

from app.models import TeamRole


class EventPermissions(BaseModel):
    """Роль пользователя в команде мероприятия; role не передаётся, если он не в команде."""

    event_id: uuid.UUID
    user_id: uuid.UUID
    is_member: bool
    role: TeamRole | None = None
