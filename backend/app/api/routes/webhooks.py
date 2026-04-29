from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.services.lead_workflow_service import LeadWorkflowService
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.database import get_db_session


router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


def get_whatsapp_client() -> MetaWhatsAppClient:
    return MetaWhatsAppClient()


def get_lead_workflow_service() -> LeadWorkflowService:
    return LeadWorkflowService()


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
    whatsapp_client: MetaWhatsAppClient = Depends(get_whatsapp_client),
) -> dict[str, int | str]:
    processed_count = 0
    duplicate_count = 0

    for message in whatsapp_client.extract_messages(payload):
        result = await workflow_service.handle_inbound_message(session, message)
        if result.is_duplicate:
            duplicate_count += 1
            continue
        if result.prompts:
            await whatsapp_client.send_prompts(message.whatsapp_number, result.prompts)
        processed_count += 1

    return {
        "status": "accepted",
        "processed": processed_count,
        "duplicates": duplicate_count,
    }