import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.api.routes.webhooks import get_whatsapp_client
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.database import Base, get_db_session
from backend.app.main import create_app
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
    assert stub_client.sent_payloads[0][1]["interactive"]["type"] == "list"

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