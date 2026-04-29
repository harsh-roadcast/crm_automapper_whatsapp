from backend.app.api.services.conversation_service import ConversationService, ConversationState
from backend.app.models.lead import LeadStatus


def test_happy_path_qualifies_lead() -> None:
    service = ConversationService()
    state = ConversationState()

    result = service.start_conversation(state)
    assert result.current_step == "ask_name"

    service.advance("Harsh Krishnatre", state)
    service.advance("medium", state)
    service.advance("Roadcast", state)
    service.advance("harsh@roadcast.in", state)
    service.advance("visibility", state)
    result = service.advance("no", state)

    lead_payload = service.build_lead_payload("+919876543210", state)

    assert result.is_complete is True
    assert result.lead_status is LeadStatus.qualified
    assert lead_payload["name"] == "Harsh Krishnatre"
    assert lead_payload["fleet_size"] == "Medium Fleet — 20 to 100 vehicles/assets"
    assert lead_payload["pain_points"] == ["Real-time fleet visibility & tracking"]
    assert lead_payload["lead_status"] == LeadStatus.qualified.value


def test_invalid_email_reprompts_without_progressing() -> None:
    service = ConversationService()
    state = ConversationState(current_step="ask_work_email", responses={"name": "Harsh"})

    result = service.advance("invalid-email", state)

    assert result.current_step == "ask_work_email"
    assert result.lead_status is LeadStatus.in_progress
    assert result.prompts[0].text == "Please share a valid work email address."
    assert len(result.prompts) == 2


def test_pain_point_prompt_paginates_for_whatsapp_limits() -> None:
    service = ConversationService()
    state = ConversationState(
        current_step="ask_work_email",
        responses={
            "name": "Harsh",
            "fleet_size": "Medium Fleet — 20 to 100 vehicles/assets",
            "company_name": "Roadcast",
        },
    )

    first_prompt = service.advance("harsh@roadcast.in", state)

    assert first_prompt.prompts[0].options[-1].id == "__more__"

    second_prompt = service.advance("__more__", state)

    assert second_prompt.prompts[0].options[0].id == "insurance"
    assert second_prompt.prompts[0].options[-1].id == "__back__"