import asyncio

from celery import Celery

from backend.app.api.services.inactivity_service import InactivityService
from backend.app.api.services.lead_sync_service import LeadSyncService
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.config import get_settings
from backend.app.core.database import SessionLocal


settings = get_settings()
celery_app = Celery("crm_automapper")
celery_app.conf.update(
    broker_url=settings.redis_url,
    result_backend=settings.redis_url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)


@celery_app.task(name="tasks.handle_inactivity_timeout")
def handle_inactivity_timeout(whatsapp_number: str) -> bool:
    return asyncio.run(_handle_inactivity_timeout_async(whatsapp_number))


async def _handle_inactivity_timeout_async(whatsapp_number: str) -> bool:
    inactivity_service = InactivityService()
    sync_service = LeadSyncService()
    whatsapp_client = MetaWhatsAppClient()

    async with SessionLocal() as session:
        return await inactivity_service.handle_timeout(
            session,
            whatsapp_number,
            whatsapp_client=whatsapp_client,
            lead_sync_service=sync_service,
        )