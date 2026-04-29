import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.api.services.lead_sync_service import LeadSyncService
from backend.app.api.services.zoho_service import ZohoSyncResult
from backend.app.core.database import Base
from backend.app.models.lead import Lead, LeadStatus
from backend.app.models.sync_log import SyncLog, SyncStatus


class StubZohoLeadClient:
    async def upsert_lead(self, lead: Lead, *, incomplete: bool = False) -> ZohoSyncResult:
        return ZohoSyncResult(
            operation="update" if lead.zoho_lead_id else "create",
            zoho_lead_id=lead.zoho_lead_id or "zoho-123",
            request_payload={"phone": lead.whatsapp_number, "incomplete": incomplete},
            response_payload={"status": "ok"},
        )


def test_lead_sync_updates_status_and_writes_log() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def run() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            lead = Lead(
                whatsapp_number="919876543210",
                name="Harsh",
                company_name="Roadcast",
                lead_status=LeadStatus.qualified,
            )
            session.add(lead)
            await session.commit()

        service = LeadSyncService(zoho_client=StubZohoLeadClient())

        async with session_factory() as session:
            synced = await service.sync_by_whatsapp_number(session, "919876543210", incomplete=False)
            assert synced is True

        async with session_factory() as session:
            lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == "919876543210"))
            sync_log = await session.scalar(select(SyncLog).where(SyncLog.lead_id == lead.id))

            assert lead is not None
            assert lead.zoho_lead_id == "zoho-123"
            assert lead.lead_status is LeadStatus.synced
            assert sync_log is not None
            assert sync_log.status is SyncStatus.success

        async with session_factory() as session:
            synced = await service.sync_by_whatsapp_number(session, "919876543210", incomplete=True)
            assert synced is True

        async with session_factory() as session:
            lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == "919876543210"))
            assert lead is not None
            assert lead.lead_status is LeadStatus.incomplete

        await engine.dispose()

    asyncio.run(run())