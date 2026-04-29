from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.services.conversation_service import ConversationService, ConversationState, Prompt
from backend.app.api.services.whatsapp_service import IncomingWhatsAppMessage
from backend.app.models.conversation import Conversation, ConversationStatus
from backend.app.models.lead import Lead, LeadStatus
from backend.app.models.message_log import MessageDirection, MessageLog


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    prompts: list[Prompt]
    lead_status: LeadStatus
    is_duplicate: bool = False
    is_complete: bool = False


class LeadWorkflowService:
    def __init__(self, conversation_service: ConversationService | None = None) -> None:
        self.conversation_service = conversation_service or ConversationService()

    async def handle_inbound_message(
        self,
        session: AsyncSession,
        message: IncomingWhatsAppMessage,
    ) -> WorkflowResult:
        existing_message = await session.scalar(
            select(MessageLog).where(MessageLog.external_message_id == message.message_id)
        )
        if existing_message is not None:
            return WorkflowResult(prompts=[], lead_status=LeadStatus.in_progress, is_duplicate=True)

        conversation = await session.scalar(
            select(Conversation).where(Conversation.whatsapp_number == message.whatsapp_number)
        )
        lead = await session.scalar(select(Lead).where(Lead.whatsapp_number == message.whatsapp_number))

        if conversation is None:
            state = ConversationState()
            result = self.conversation_service.start_conversation(state)
            conversation = Conversation(
                whatsapp_number=message.whatsapp_number,
                current_step=result.current_step,
                responses=result.responses,
                last_message_id=message.message_id,
                status=ConversationStatus.active,
            )
            session.add(conversation)
        else:
            state = ConversationState(
                current_step=conversation.current_step,
                responses=dict(conversation.responses or {}),
            )
            result = self.conversation_service.advance(message.text, state)
            conversation.current_step = result.current_step
            conversation.responses = result.responses
            conversation.last_message_id = message.message_id
            conversation.status = ConversationStatus.completed if result.is_complete else ConversationStatus.active

        if lead is None:
            lead = Lead(whatsapp_number=message.whatsapp_number)
            session.add(lead)

        self._sync_lead_from_state(lead, message.whatsapp_number, state)

        session.add(
            MessageLog(
                external_message_id=message.message_id,
                whatsapp_number=message.whatsapp_number,
                direction=MessageDirection.inbound,
                message_type=message.message_type,
                payload=message.raw_payload,
            )
        )
        await session.commit()

        return WorkflowResult(
            prompts=result.prompts,
            lead_status=result.lead_status,
            is_complete=result.is_complete,
        )

    def _sync_lead_from_state(self, lead: Lead, whatsapp_number: str, state: ConversationState) -> None:
        payload = self.conversation_service.build_lead_payload(whatsapp_number, state)
        if payload["name"]:
            lead.name = str(payload["name"])
        if payload["fleet_size"]:
            lead.fleet_size = str(payload["fleet_size"])
        if payload["company_name"]:
            lead.company_name = str(payload["company_name"])
        if payload["work_email"]:
            lead.work_email = str(payload["work_email"])

        lead.whatsapp_number = whatsapp_number
        lead.last_question_key = str(payload["last_question_key"])
        lead.other_problem_text = str(payload["other_problem_text"] or "") or None

        pain_points = payload["pain_points"]
        if isinstance(pain_points, list):
            lead.pain_points = pain_points

        if payload["lead_status"] == LeadStatus.qualified.value:
            lead.lead_status = LeadStatus.qualified
        else:
            lead.lead_status = LeadStatus.in_progress