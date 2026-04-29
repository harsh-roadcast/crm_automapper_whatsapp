import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageLog(Base):
    __tablename__ = "message_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_message_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    whatsapp_number: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection),
        default=MessageDirection.inbound,
        nullable=False,
    )
    message_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )