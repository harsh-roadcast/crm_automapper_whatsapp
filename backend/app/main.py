from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.api.routes.health import router as health_router
from backend.app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "crm-automapper-whatsapp", "status": "ok"}

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()