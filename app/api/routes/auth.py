from fastapi import APIRouter, Depends

from app.core.security.current_user import get_current_user
from app.domain import User
from app.domain.users.schemas import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:  # noqa: B008
    """Return the currently authenticated user."""
    return current_user
