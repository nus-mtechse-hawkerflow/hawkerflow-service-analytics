from fastapi import APIRouter

health_router = APIRouter()


@health_router.get("/health")
async def health() -> dict[str, str]:
    """Process liveness only.

    Deliberately does not connect to the database and reports no
    configuration, so it is safe to expose without credentials.
    """
    return {"status": "ok", "service": "analytics"}
