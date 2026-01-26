from fastapi import APIRouter

from app.api.routers.admin_templates import health_get, health_run

router = APIRouter()
router.include_router(health_get.router)
router.include_router(health_run.router)

__all__ = ["router"]
