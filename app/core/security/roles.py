from fastapi import HTTPException, status

from app.domain import User


def ensure_recruiter(user: User) -> None:
    """Enforce recruiter role."""
    if getattr(user, "role", None) != "recruiter":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )


def ensure_recruiter_or_none(user: User) -> None:
    """Allow recruiter or unset role (legacy)."""
    if getattr(user, "role", None) not in {None, "recruiter"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )
