from fastapi import APIRouter

from app.api.routers.submissions_routes import detail, list

router = APIRouter(tags=["submissions"])
router.include_router(detail.router)
router.include_router(list.router)

__all__ = ["router"]
