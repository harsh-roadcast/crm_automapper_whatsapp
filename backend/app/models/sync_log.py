import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class SyncStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("leads.id"), nullable=False)
    target_system: Mapped[str] = mapped_column(String(64), default="zoho", nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus),
        default=SyncStatus.pending,
        nullable=False,
    )
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )