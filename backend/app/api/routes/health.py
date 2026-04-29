from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readiness() -> dict[str, str]:
    return {"status": "ready"}