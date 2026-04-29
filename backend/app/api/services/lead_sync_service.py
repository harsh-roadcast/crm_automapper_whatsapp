from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.services.zoho_service import ZohoLeadClient
from backend.app.models.lead import Lead, LeadStatus
from backend.app.models.sync_log import SyncLog, SyncStatus


class LeadSyncService:
    def __init__(self, zoho_client: ZohoLeadClient | None = None) -> None:
        self.zoho_client = zoho_client or ZohoLeadClient()

    async def sync_by_whatsapp_number(
        self,
        session: AsyncSession,
        whatsapp_number: str,
        *,
        incomplete: bool = False,
    ) -> bool:
        lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == whatsapp_number))
        if lead is None:
            return False
        return await self.sync_lead(session, lead, incomplete=incomplete)

    async def sync_lead(self, session: AsyncSession, lead: Lead, *, incomplete: bool = False) -> bool:
        operation = "partial_upsert" if incomplete else "upsert"
        sync_log = SyncLog(
            lead_id=lead.id,
            operation=operation,
            status=SyncStatus.pending,
            request_payload={},
        )
        session.add(sync_log)
        await session.flush()

        try:
            result = await self.zoho_client.upsert_lead(lead, incomplete=incomplete)
            lead.zoho_lead_id = result.zoho_lead_id or lead.zoho_lead_id
            lead.lead_status = LeadStatus.incomplete if incomplete else LeadStatus.synced

            sync_log.status = SyncStatus.success
            sync_log.operation = result.operation
            sync_log.request_payload = result.request_payload
            sync_log.response_payload = result.response_payload
            sync_log.error_message = None

            await session.commit()
            return True
        except Exception as exc:
            sync_log.status = SyncStatus.failed
            sync_log.error_message = str(exc)
            await session.commit()
            return False
