import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class ConversationStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    incomplete = "incomplete"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    whatsapp_number: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus),
        default=ConversationStatus.active,
        nullable=False,
    )
    current_step: Mapped[str] = mapped_column(String(64), default="welcome", nullable=False)
    last_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    responses: Mapped[dict[str, str | list[str]]] = mapped_column(JSON, default=dict)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )