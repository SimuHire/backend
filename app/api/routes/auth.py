from fastapi import APIRouter, Depends

from app.domains import User
from app.domains.users.schemas import UserRead
from app.infra.security.current_user import get_current_user

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_me(current_user: User = Depends(get_current_user)) -> User:  # noqa: B008
    """Return the currently authenticated user."""
    return current_user
