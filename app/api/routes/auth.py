from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.domains import User
from app.domains.users.schemas import UserRead
from app.infra.security import rate_limit
from app.infra.security.current_user import get_current_user

router = APIRouter()

AUTH_ME_RATE_LIMIT = rate_limit.RateLimitRule(limit=60, window_seconds=60.0)


@router.get("/me", response_model=UserRead)
async def read_me(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Return the currently authenticated user."""
    if rate_limit.rate_limit_enabled():
        key = rate_limit.rate_limit_key("auth_me", rate_limit.client_id(request))
        rate_limit.limiter.allow(key, AUTH_ME_RATE_LIMIT)
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    """Stateless logout endpoint; backend does not manage sessions or redirects."""
    response.headers["Cache-Control"] = "no-store"
