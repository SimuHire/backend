from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_simulations():
    """List available simulations (placeholder)."""
    return []
