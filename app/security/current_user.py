from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import async_session_maker
from app.models.user import User
from app.security import auth0

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials

    try:
        claims = auth0.decode_auth0_token(token)
    except auth0.Auth0Error as exc:
        raise exc

    email_value = claims.get("email") or claims.get("https://simuhire.com/email")
    if not isinstance(email_value, str) or not email_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email claim missing",
        )

    email = email_value

    name_value = claims.get("name") or claims.get("https://simuhire.com/name")
    if isinstance(name_value, str) and name_value.strip():
        name = name_value.strip()
    else:
        name = email.split("@")[0]

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                name=name,
                email=email,
                role="recruiter",
                password_hash="",
            )
            session.add(user)

            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                result = await session.execute(select(User).where(User.email == email))
                user = result.scalar_one()
            else:
                await session.refresh(user)

    return user
