from dataclasses import dataclass

import httpx

from backend.app.api.services.conversation_service import Prompt
from backend.app.core.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class IncomingWhatsAppMessage:
    message_id: str
    whatsapp_number: str
    profile_name: str | None
    text: str
    message_type: str
    raw_payload: dict


class MetaWhatsAppClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def is_valid_verification_token(self, token: str) -> bool:
        return bool(self.settings.whatsapp_verify_token) and token == self.settings.whatsapp_verify_token

    def extract_messages(self, payload: dict) -> list[IncomingWhatsAppMessage]:
        extracted_messages: list[IncomingWhatsAppMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {
                    contact.get("wa_id"): contact.get("profile", {}).get("name")
                    for contact in value.get("contacts", [])
                }
                for message in value.get("messages", []):
                    text = self._extract_message_text(message)
                    whatsapp_number = message.get("from", "")
                    if not text or not whatsapp_number:
                        continue
                    extracted_messages.append(
                        IncomingWhatsAppMessage(
                            message_id=message.get("id", ""),
                            whatsapp_number=whatsapp_number,
                            profile_name=contacts.get(whatsapp_number),
                            text=text,
                            message_type=message.get("type", "unknown"),
                            raw_payload=message,
                        )
                    )
        return extracted_messages

    def build_outbound_payloads(self, whatsapp_number: str, prompts: list[Prompt]) -> list[dict]:
        payloads: list[dict] = []
        for prompt in prompts:
            if prompt.kind == "text":
                payloads.append(self._text_payload(whatsapp_number, prompt.text))
                continue
            if prompt.kind == "buttons":
                payloads.append(self._button_payload(whatsapp_number, prompt))
                continue
            if prompt.kind == "list":
                payloads.append(self._list_payload(whatsapp_number, prompt))
        return payloads

    async def send_prompts(self, whatsapp_number: str, prompts: list[Prompt]) -> list[dict]:
        payloads = self.build_outbound_payloads(whatsapp_number, prompts)
        if not self.settings.whatsapp_access_token or not self.settings.whatsapp_phone_number_id:
            return payloads

        endpoint = (
            f"https://graph.facebook.com/{self.settings.whatsapp_graph_api_version}/"
            f"{self.settings.whatsapp_phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self.settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        responses: list[dict] = []
        async with httpx.AsyncClient(timeout=15.0) as client:
            for payload in payloads:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                responses.append(response.json())
        return responses

    def _extract_message_text(self, message: dict) -> str | None:
        message_type = message.get("type")
        if message_type == "text":
            return message.get("text", {}).get("body")
        if message_type == "interactive":
            interactive = message.get("interactive", {})
            if "list_reply" in interactive:
                return interactive["list_reply"].get("id") or interactive["list_reply"].get("title")
            if "button_reply" in interactive:
                return interactive["button_reply"].get("id") or interactive["button_reply"].get("title")
        if message_type == "button":
            return message.get("button", {}).get("payload")
        return None

    def _base_payload(self, whatsapp_number: str) -> dict:
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": whatsapp_number,
        }

    def _text_payload(self, whatsapp_number: str, text: str) -> dict:
        payload = self._base_payload(whatsapp_number)
        payload.update({"type": "text", "text": {"body": text}})
        return payload

    def _button_payload(self, whatsapp_number: str, prompt: Prompt) -> dict:
        buttons = []
        for index, option in enumerate(prompt.options[:3]):
            buttons.append(
                {
                    "type": "reply",
                    "reply": {
                        "id": option.id,
                        "title": option.title[:20],
                    },
                }
            )
        payload = self._base_payload(whatsapp_number)
        payload.update(
            {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": prompt.text},
                    "action": {"buttons": buttons},
                },
            }
        )
        return payload

    def _list_payload(self, whatsapp_number: str, prompt: Prompt) -> dict:
        if len(prompt.options) > 10:
            raise ValueError("WhatsApp list messages support at most 10 rows across sections.")

        rows = []
        for option in prompt.options:
            rows.append(
                {
                    "id": option.id,
                    "title": option.title[:24],
                    "description": (option.description or option.label)[:72],
                }
            )

        payload = self._base_payload(whatsapp_number)
        payload.update(
            {
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": prompt.text},
                    "action": {
                        "button": "Choose option",
                        "sections": [{"title": "Options", "rows": rows}],
                    },
                },
            }
        )
        return payload