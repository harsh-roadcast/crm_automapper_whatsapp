import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.api.services.inactivity_service import InactivityService
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.config import Settings
from backend.app.core.database import Base
from backend.app.models.conversation import Conversation, ConversationStatus
from backend.app.models.lead import Lead, LeadStatus


class StubRedis:
    def __init__(self) -> None:
        self.values: dict[str, tuple[int, str]] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = (ttl, value)

    async def get(self, key: str) -> str | None:
        item = self.values.get(key)
        return item[1] if item else None


class RecordingScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def __call__(self, whatsapp_number: str, timeout_seconds: int) -> None:
        self.calls.append((whatsapp_number, timeout_seconds))


class StubWhatsAppClient(MetaWhatsAppClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, list]] = []

    async def send_prompts(self, whatsapp_number: str, prompts: list) -> list[dict]:
        self.calls.append((whatsapp_number, prompts))
        return []


class StubLeadSyncService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    async def sync_by_whatsapp_number(self, session, whatsapp_number: str, *, incomplete: bool = False) -> bool:
        self.calls.append((whatsapp_number, incomplete))
        return True


def test_register_activity_sets_ttl_and_schedules_timeout() -> None:
    settings = Settings(inactivity_timeout_minutes=10)
    redis = StubRedis()
    scheduler = RecordingScheduler()
    service = InactivityService(settings=settings, redis_client=redis, task_scheduler=scheduler)

    asyncio.run(service.register_activity("919876543210"))

    assert redis.values == {"inactivity:919876543210": (600, "active")}
    assert scheduler.calls == [("919876543210", 600)]


def test_handle_timeout_marks_records_incomplete_and_triggers_sync() -> None:
    settings = Settings(inactivity_timeout_minutes=10)
    redis = StubRedis()
    service = InactivityService(settings=settings, redis_client=redis, task_scheduler=RecordingScheduler())
    whatsapp_client = StubWhatsAppClient()
    lead_sync_service = StubLeadSyncService()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        stale_time = datetime.now(timezone.utc) - timedelta(minutes=20)

        async with session_factory() as session:
            session.add(
                Conversation(
                    whatsapp_number="919876543210",
                    current_step="ask_company_name",
                    status=ConversationStatus.active,
                    responses={"name": "Harsh"},
                )
            )
            session.add(
                Lead(
                    whatsapp_number="919876543210",
                    name="Harsh",
                    company_name="Roadcast",
                    lead_status=LeadStatus.in_progress,
                    last_question_key="ask_company_name",
                    updated_at=stale_time,
                )
            )
            await session.commit()

        async with session_factory() as session:
            handled = await service.handle_timeout(
                session,
                "919876543210",
                whatsapp_client=whatsapp_client,
                lead_sync_service=lead_sync_service,
            )
            assert handled is True

        async with session_factory() as session:
            conversation = await session.scalar(
                select(Conversation).where(Conversation.whatsapp_number == "919876543210")
            )
            lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == "919876543210"))

            assert conversation is not None
            assert conversation.status is ConversationStatus.incomplete
            assert lead is not None
            assert lead.lead_status is LeadStatus.incomplete

        assert lead_sync_service.calls == [("919876543210", True)]
        assert len(whatsapp_client.calls) == 1

        await engine.dispose()

    asyncio.run(run())