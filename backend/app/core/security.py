from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings
from app.core.response import ErrorCode

ALGORITHM = "HS256"


def create_access_token(
    user_id: int,
    username: str,
    role: str,
    token_version: int,
) -> str:
    """Create a signed JWT access token for the given user."""
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "token_version": token_version,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """
    Decode and verify a JWT token.

    Returns the decoded payload dict.
    Raises HTTPException(401) with AUTH_TOKEN_EXPIRED on any failure.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": ErrorCode.AUTH_TOKEN_EXPIRED, "message": "Token 已过期或无效"},
        )
