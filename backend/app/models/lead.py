import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class LeadStatus(str, enum.Enum):
    in_progress = "in_progress"
    qualified = "qualified"
    incomplete = "incomplete"
    synced = "synced"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    whatsapp_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fleet_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pain_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    other_problem_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_question_key: Mapped[str] = mapped_column(String(64), default="welcome", nullable=False)
    lead_status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus),
        default=LeadStatus.in_progress,
        nullable=False,
    )
    zoho_lead_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
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