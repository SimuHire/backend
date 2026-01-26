from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Liveness probe endpoint."""
    return {"status": "ok"}
