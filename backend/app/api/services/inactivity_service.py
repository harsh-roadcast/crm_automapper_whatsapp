from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.services.conversation_service import Prompt
from backend.app.api.services.lead_sync_service import LeadSyncService
from backend.app.api.services.whatsapp_service import MetaWhatsAppClient
from backend.app.core.config import Settings, get_settings
from backend.app.core.redis import get_redis_client
from backend.app.models.conversation import Conversation, ConversationStatus
from backend.app.models.lead import Lead, LeadStatus


class InactivityService:
    def __init__(
        self,
        settings: Settings | None = None,
        redis_client=None,
        task_scheduler: Callable[[str, int], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.redis = redis_client or get_redis_client()
        self.task_scheduler = task_scheduler or self._schedule_timeout_task

    async def register_activity(self, whatsapp_number: str) -> None:
        timeout_seconds = self.settings.inactivity_timeout_minutes * 60
        try:
            await self.redis.setex(f"inactivity:{whatsapp_number}", timeout_seconds, "active")
        except Exception:
            # Fail open in local development if Redis is unavailable.
            return

        try:
            self.task_scheduler(whatsapp_number, timeout_seconds)
        except Exception:
            # Fail open if Celery or the broker is unavailable locally.
            return

    async def handle_timeout(
        self,
        session: AsyncSession,
        whatsapp_number: str,
        *,
        whatsapp_client: MetaWhatsAppClient,
        lead_sync_service: LeadSyncService,
    ) -> bool:
        try:
            still_active = await self.redis.get(f"inactivity:{whatsapp_number}")
        except Exception:
            still_active = None
        if still_active:
            return False

        conversation = await session.scalar(
            select(Conversation).where(Conversation.whatsapp_number == whatsapp_number)
        )
        lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == whatsapp_number))
        if conversation is None or lead is None:
            return False
        if conversation.status == ConversationStatus.completed:
            return False

        if self._recently_active(lead.updated_at):
            return False

        conversation.status = ConversationStatus.incomplete
        lead.lead_status = LeadStatus.incomplete
        await session.commit()

        try:
            await whatsapp_client.send_prompts(
                whatsapp_number,
                [
                    Prompt(
                        key="reengage",
                        kind="text",
                        text=(
                            "We are here whenever you are ready. Reply to continue your lead qualification, "
                            "and we will connect you with the right fleet expert."
                        ),
                    )
                ],
            )
        except Exception:
            pass

        await lead_sync_service.sync_by_whatsapp_number(session, whatsapp_number, incomplete=True)
        return True

    def _recently_active(self, updated_at: datetime) -> bool:
        threshold = datetime.now(timezone.utc) - timedelta(minutes=self.settings.inactivity_timeout_minutes)
        aware_updated_at = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
        return aware_updated_at >= threshold

    def _schedule_timeout_task(self, whatsapp_number: str, timeout_seconds: int) -> None:
        from backend.app.api.tasks.reengagement_tasks import handle_inactivity_timeout

        handle_inactivity_timeout.apply_async(args=[whatsapp_number], countdown=timeout_seconds)