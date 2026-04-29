from fastapi import APIRouter

from backend.app.api.routes.webhooks import router as webhook_router


api_router = APIRouter()
api_router.include_router(webhook_router)