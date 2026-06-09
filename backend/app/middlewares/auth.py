from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.response import ErrorCode
from app.core.security import verify_token
from app.core.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _http_err(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> User:
    """
    Validate Bearer token and return the active User.

    Check order (per Permission spec §10):
    1. Token present
    2. Token valid / not expired
    3. User exists and not deleted
    4. User not disabled
    """
    if not token:
        raise _http_err(ErrorCode.AUTH_TOKEN_MISSING, "缺少 Token", status.HTTP_401_UNAUTHORIZED)

    payload = verify_token(token)  # raises 401 on failure

    user_id = int(payload["sub"])
    db_token_version: int = payload.get("token_version", 0)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user: User | None = result.scalar_one_or_none()

    if user is None or user.deleted_at is not None:
        raise _http_err(ErrorCode.AUTH_TOKEN_MISSING, "用户不存在", status.HTTP_401_UNAUTHORIZED)

    if user.token_version != db_token_version:
        raise _http_err(ErrorCode.AUTH_TOKEN_EXPIRED, "Token 已过期", status.HTTP_401_UNAUTHORIZED)

    if user.status == "disabled":
        raise _http_err(ErrorCode.AUTH_USER_DISABLED, "账号已停用", status.HTTP_403_FORBIDDEN)

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Require the authenticated user to have role=admin and a changed password.

    All admin/* routes are business routes, so the force-change-password rule applies.
    """
    if current_user.password_changed_at is None:
        raise _http_err(
            ErrorCode.AUTH_FORCE_CHANGE_PASSWORD,
            "请先修改初始密码",
            status.HTTP_403_FORBIDDEN,
        )
    if current_user.role != "admin":
        raise _http_err(ErrorCode.PERMISSION_DENIED, "无权限访问", status.HTTP_403_FORBIDDEN)
    return current_user


async def get_current_user_optional(token: str | None = Depends(oauth2_scheme)) -> User | None:
    """有 token 则解析返回 User，无 token 或 token 无效均返回 None，不抛异常。"""
    if not token:
        return None
    try:
        payload = verify_token(token)
        user_id = int(payload["sub"])
        db_token_version: int = payload.get("token_version", 0)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user: User | None = result.scalar_one_or_none()
        if user is None or user.deleted_at is not None:
            return None
        if user.token_version != db_token_version:
            return None
        if user.status == "disabled":
            return None
        return user
    except Exception:
        return None


async def require_password_changed(current_user: User = Depends(get_current_user)) -> User:
    """
    Require the user to have already changed their initial password.

    White-listed endpoints (must NOT use this dependency):
      GET  /api/auth/me
      POST /api/auth/change-password
      POST /api/auth/logout
    """
    if current_user.password_changed_at is None:
        raise _http_err(
            ErrorCode.AUTH_FORCE_CHANGE_PASSWORD,
            "请先修改初始密码",
            status.HTTP_403_FORBIDDEN,
        )
    return current_user
