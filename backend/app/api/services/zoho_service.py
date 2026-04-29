from dataclasses import dataclass

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.models.lead import Lead


@dataclass(frozen=True, slots=True)
class ZohoSyncResult:
    operation: str
    zoho_lead_id: str
    request_payload: dict
    response_payload: dict


class ZohoLeadClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def upsert_lead(self, lead: Lead, *, incomplete: bool = False) -> ZohoSyncResult:
        token = await self._get_access_token()
        if token is None:
            synthetic_id = lead.zoho_lead_id or f"offline-{lead.whatsapp_number}"
            payload = self._build_zoho_payload(lead, incomplete=incomplete)
            return ZohoSyncResult(
                operation="offline",
                zoho_lead_id=synthetic_id,
                request_payload=payload,
                response_payload={"offline": True},
            )

        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Zoho-oauthtoken {token}"}
            existing_lead_id = await self._find_lead_id_by_whatsapp(client, headers, lead.whatsapp_number)
            payload = self._build_zoho_payload(lead, incomplete=incomplete)

            if existing_lead_id:
                update_payload = {"data": [{**payload, "id": existing_lead_id}]}
                response = await client.put(
                    f"{self.settings.zoho_base_url}/crm/v7/{self.settings.zoho_leads_module}",
                    headers=headers,
                    json=update_payload,
                )
                response.raise_for_status()
                body = response.json()
                return ZohoSyncResult(
                    operation="update",
                    zoho_lead_id=existing_lead_id,
                    request_payload=update_payload,
                    response_payload=body,
                )

            create_payload = {"data": [payload]}
            response = await client.post(
                f"{self.settings.zoho_base_url}/crm/v7/{self.settings.zoho_leads_module}",
                headers=headers,
                json=create_payload,
            )
            response.raise_for_status()
            body = response.json()
            created_id = (
                body.get("data", [{}])[0].get("details", {}).get("id")
                or body.get("data", [{}])[0].get("details", {}).get("record_id")
                or ""
            )
            return ZohoSyncResult(
                operation="create",
                zoho_lead_id=created_id,
                request_payload=create_payload,
                response_payload=body,
            )

    async def _get_access_token(self) -> str | None:
        if not all(
            [
                self.settings.zoho_client_id,
                self.settings.zoho_client_secret,
                self.settings.zoho_refresh_token,
            ]
        ):
            return None

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.settings.zoho_base_url}/oauth/v2/token",
                params={
                    "refresh_token": self.settings.zoho_refresh_token,
                    "client_id": self.settings.zoho_client_id,
                    "client_secret": self.settings.zoho_client_secret,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json().get("access_token")

    async def _find_lead_id_by_whatsapp(self, client: httpx.AsyncClient, headers: dict, whatsapp_number: str) -> str | None:
        criteria = f"(WhatsApp_Number:equals:{whatsapp_number})"
        response = await client.get(
            f"{self.settings.zoho_base_url}/crm/v7/{self.settings.zoho_leads_module}/search",
            headers=headers,
            params={"criteria": criteria},
        )
        if response.status_code == 204:
            return None
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = response.json()
        records = body.get("data", [])
        if not records:
            return None
        return records[0].get("id")

    def _build_zoho_payload(self, lead: Lead, *, incomplete: bool = False) -> dict:
        last_name = (lead.name or "Unknown").strip() or "Unknown"
        pain_points = lead.pain_points or []
        lead_status = "Incomplete" if incomplete else "Qualified"

        return {
            "Last_Name": last_name,
            "Company": lead.company_name or "Unknown",
            "Email": lead.work_email,
            "WhatsApp_Number": lead.whatsapp_number,
            "Fleet_Size": lead.fleet_size,
            "Pain_Points": ", ".join(pain_points),
            "Other_Problem_Text": lead.other_problem_text,
            "Lead_Status": lead_status,
            "Lead_Source": "WhatsApp Chatbot",
        }