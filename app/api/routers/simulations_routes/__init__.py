from fastapi import APIRouter

from app.api.routers.simulations_routes import (
    candidates,
    create,
    detail,
    invite_create,
    invite_resend,
    list_simulations,
)

router = APIRouter()
router.include_router(list_simulations.router)
router.include_router(create.router)
router.include_router(detail.router, prefix="/simulations")
router.include_router(invite_create.router, prefix="/simulations")
router.include_router(invite_resend.router, prefix="/simulations")
router.include_router(candidates.router, prefix="/simulations")

__all__ = ["router"]
