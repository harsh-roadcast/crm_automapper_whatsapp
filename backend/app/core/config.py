from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Roadcast CRM Automapper WhatsApp"
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    postgres_dsn: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/crm_automapper"
    )
    redis_url: str = "redis://localhost:6379/0"
    inactivity_timeout_minutes: int = 10

    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_graph_api_version: str = "v25.0"

    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_refresh_token: str = ""
    zoho_base_url: str = "https://www.zohoapis.in"
    zoho_leads_module: str = "Leads"


@lru_cache
def get_settings() -> Settings:
    return Settings()