from fastapi import APIRouter

from app.api.routes.tasks import init, poll, run, status, submit

router = APIRouter()
router.include_router(init.router)
router.include_router(status.router)
router.include_router(run.router)
router.include_router(poll.router)
router.include_router(submit.router)

__all__ = ["router"]
