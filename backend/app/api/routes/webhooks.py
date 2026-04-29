from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.services.inactivity_service import InactivityService
from backend.app.api.services.lead_sync_service import LeadSyncService
from backend.app.api.services.lead_workflow_service import LeadWorkflowService
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.database import get_db_session


router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


def get_whatsapp_client() -> MetaWhatsAppClient:
    return MetaWhatsAppClient()


def get_lead_workflow_service() -> LeadWorkflowService:
    return LeadWorkflowService()


def get_lead_sync_service() -> LeadSyncService:
    return LeadSyncService()


def get_inactivity_service() -> InactivityService:
    return InactivityService()


@router.get("")
async def verify_whatsapp_webhook(
    mode: str = Query(alias="hub.mode"),
    verify_token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
    whatsapp_client: MetaWhatsAppClient = Depends(get_whatsapp_client),
) -> PlainTextResponse:
    if mode != "subscribe" or not whatsapp_client.is_valid_verification_token(verify_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook verification token.")
    return PlainTextResponse(challenge)


@router.post("")
async def receive_whatsapp_webhook(
    payload: dict,
    session: AsyncSession = Depends(get_db_session),
    workflow_service: LeadWorkflowService = Depends(get_lead_workflow_service),
    lead_sync_service: LeadSyncService = Depends(get_lead_sync_service),
    inactivity_service: InactivityService = Depends(get_inactivity_service),
    whatsapp_client: MetaWhatsAppClient = Depends(get_whatsapp_client),
) -> dict[str, int | str]:
    processed_count = 0
    duplicate_count = 0
    synced_count = 0

    for message in whatsapp_client.extract_messages(payload):
        result = await workflow_service.handle_inbound_message(session, message)
        if result.is_duplicate:
            duplicate_count += 1
            continue
        await inactivity_service.register_activity(message.whatsapp_number)
        if result.prompts:
            await whatsapp_client.send_prompts(message.whatsapp_number, result.prompts)
        if result.is_complete:
            sync_done = await lead_sync_service.sync_by_whatsapp_number(
                session,
                message.whatsapp_number,
                incomplete=False,
            )
            if sync_done:
                synced_count += 1
        processed_count += 1

    return {
        "status": "accepted",
        "processed": processed_count,
        "duplicates": duplicate_count,
        "synced": synced_count,
    }