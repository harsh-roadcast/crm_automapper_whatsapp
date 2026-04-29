import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.api.routes.webhooks import get_inactivity_service, get_lead_sync_service, get_whatsapp_client
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.database import Base, get_db_session
from backend.app.main import create_app
from backend.app.models.conversation import Conversation, ConversationStatus
from backend.app.models.lead import Lead, LeadStatus


class StubWhatsAppClient(MetaWhatsAppClient):
    def __init__(self) -> None:
        super().__init__()
        self.settings.whatsapp_verify_token = "verify-token"
        self.sent_payloads: list[list[dict]] = []

    async def send_prompts(self, whatsapp_number: str, prompts: list) -> list[dict]:
        payloads = self.build_outbound_payloads(whatsapp_number, prompts)
        self.sent_payloads.append(payloads)
        return payloads


class StubLeadSyncService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    async def sync_by_whatsapp_number(self, session, whatsapp_number: str, *, incomplete: bool = False) -> bool:
        self.calls.append((whatsapp_number, incomplete))
        return True


class StubInactivityService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def register_activity(self, whatsapp_number: str) -> None:
        self.calls.append(whatsapp_number)


def test_whatsapp_webhook_verification_and_message_persistence() -> None:
    app = create_app()
    stub_client = StubWhatsAppClient()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def prepare_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare_database())

    async def override_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_whatsapp_client] = lambda: stub_client

    client = TestClient(app)

    verify_response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token",
            "hub.challenge": "challenge-token",
        },
    )

    assert verify_response.status_code == 200
    assert verify_response.text == "challenge-token"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "919876543210", "profile": {"name": "Harsh"}}],
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid-1",
                                    "timestamp": "1713870000",
                                    "type": "text",
                                    "text": {"body": "Hi"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }

    webhook_response = client.post("/api/v1/webhooks/whatsapp", json=payload)
    duplicate_response = client.post("/api/v1/webhooks/whatsapp", json=payload)

    assert webhook_response.status_code == 200
    assert webhook_response.json() == {"status": "accepted", "processed": 1, "duplicates": 0, "synced": 0}
    assert duplicate_response.status_code == 200
    assert duplicate_response.json() == {"status": "accepted", "processed": 0, "duplicates": 1, "synced": 0}
    assert len(stub_client.sent_payloads) == 1
    assert stub_client.sent_payloads[0][0]["type"] == "text"
    assert stub_client.sent_payloads[0][1]["type"] == "text"

    async def fetch_lead() -> Lead | None:
        async with session_factory() as session:
            return await session.scalar(select(Lead).where(Lead.whatsapp_number == "919876543210"))

    lead = asyncio.run(fetch_lead())

    assert lead is not None
    assert lead.lead_status is LeadStatus.in_progress
    assert lead.last_question_key == "ask_name"

    async def dispose_engine() -> None:
        await engine.dispose()

    asyncio.run(dispose_engine())


def test_whatsapp_webhook_completion_triggers_sync() -> None:
    app = create_app()
    stub_client = StubWhatsAppClient()
    stub_sync_service = StubLeadSyncService()
    stub_inactivity_service = StubInactivityService()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def prepare_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(prepare_database())

    async def override_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_whatsapp_client] = lambda: stub_client
    app.dependency_overrides[get_lead_sync_service] = lambda: stub_sync_service
    app.dependency_overrides[get_inactivity_service] = lambda: stub_inactivity_service

    client = TestClient(app)

    def send_message(message_id: str, text: str, *, message_type: str = "text"):
        if message_type == "text":
            payload_message = {
                "from": "919876543210",
                "id": message_id,
                "timestamp": "1713870000",
                "type": "text",
                "text": {"body": text},
            }
        else:
            payload_message = {
                "from": "919876543210",
                "id": message_id,
                "timestamp": "1713870000",
                "type": "interactive",
                "interactive": {"list_reply": {"id": text, "title": text}},
            }

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "contacts": [{"wa_id": "919876543210", "profile": {"name": "Harsh"}}],
                                "messages": [payload_message],
                            }
                        }
                    ]
                }
            ],
        }
        return client.post("/api/v1/webhooks/whatsapp", json=payload)

    send_message("wamid-1", "Hi")
    send_message("wamid-2", "Harsh Krishnatre")
    send_message("wamid-3", "medium", message_type="interactive")
    send_message("wamid-4", "Roadcast")
    send_message("wamid-5", "harsh@roadcast.in")
    send_message("wamid-6", "visibility", message_type="interactive")
    final_response = send_message("wamid-7", "no", message_type="interactive")

    assert final_response.status_code == 200
    assert final_response.json() == {"status": "accepted", "processed": 1, "duplicates": 0, "synced": 1}
    assert stub_sync_service.calls == [("919876543210", False)]
    assert stub_inactivity_service.calls == [
        "919876543210",
        "919876543210",
        "919876543210",
        "919876543210",
        "919876543210",
        "919876543210",
        "919876543210",
    ]

    async def fetch_records() -> tuple[Lead | None, Conversation | None]:
        async with session_factory() as session:
            lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == "919876543210"))
            conversation = await session.scalar(
                select(Conversation).where(Conversation.whatsapp_number == "919876543210")
            )
            return lead, conversation

    lead, conversation = asyncio.run(fetch_records())

    assert lead is not None
    assert lead.lead_status is LeadStatus.qualified
    assert lead.pain_points == ["Real-time fleet visibility & tracking"]
    assert conversation is not None
    assert conversation.status is ConversationStatus.completed

    async def dispose_engine() -> None:
        await engine.dispose()

    asyncio.run(dispose_engine())