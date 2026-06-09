from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.core.security import create_access_token
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter(prefix="/auth")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Pydantic schemas (request bodies)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _write_op_log(
    session,
    user: User,
    action: str,
    request: Request,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: dict | None = None,
) -> None:
    log = OperationLog(
        user_id=user.id,
        username=user.username,
        role=user.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    session.add(log)


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@router.post("/login", response_model=ApiResponse)
async def login(body: LoginRequest, request: Request):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.username == body.username, User.deleted_at.is_(None))
        )
        user: User | None = result.scalar_one_or_none()

    if user is None or not pwd_context.verify(body.password, user.password_hash):
        return error_response(ErrorCode.AUTH_INVALID_PASSWORD, "账号或密码错误")

    if user.status == "disabled":
        return error_response(ErrorCode.AUTH_USER_DISABLED, "账号已停用，请联系管理员")

    token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        token_version=user.token_version,
    )
    must_change = user.password_changed_at is None

    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.id == user.id)
            .values(last_login_at=now, last_active_at=now)
        )
        log = OperationLog(
            user_id=user.id,
            username=user.username,
            role=user.role,
            action="login",
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        session.add(log)
        await session.commit()

    return success_response(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 86400,
            "must_change_password": must_change,
            "user": {
                "id": user.id,
                "username": user.username,
                "real_name": user.real_name,
                "role": user.role,
                "status": user.status,
            },
        }
    )


# ---------------------------------------------------------------------------
# GET /api/auth/me   (requires login, NOT require_password_changed)
# ---------------------------------------------------------------------------

@router.get("/me", response_model=ApiResponse)
async def me(current_user: User = Depends(get_current_user)):
    return success_response(
        data={
            "id": current_user.id,
            "username": current_user.username,
            "real_name": current_user.real_name,
            "role": current_user.role,
            "status": current_user.status,
            "must_change_password": current_user.password_changed_at is None,
            "last_login_at": (
                current_user.last_login_at.isoformat() if current_user.last_login_at else None
            ),
        }
    )


# ---------------------------------------------------------------------------
# POST /api/auth/change-password  (requires login, NOT require_password_changed)
# ---------------------------------------------------------------------------

@router.post("/change-password", response_model=ApiResponse)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    if body.new_password != body.confirm_password:
        return error_response(ErrorCode.VALIDATION_ERROR, "两次输入密码不一致")

    if not pwd_context.verify(body.old_password, current_user.password_hash):
        return error_response(ErrorCode.AUTH_INVALID_PASSWORD, "旧密码错误")

    new_hash = pwd_context.hash(body.new_password)
    now = datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(
                password_hash=new_hash,
                password_changed_at=now,
                token_version=User.token_version + 1,
            )
        )
        log = OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="change_password",
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        session.add(log)
        await session.commit()

    return success_response(data=None, message="密码修改成功，请重新登录")


# ---------------------------------------------------------------------------
# POST /api/auth/logout  (requires login, NOT require_password_changed)
# ---------------------------------------------------------------------------

@router.post("/logout", response_model=ApiResponse)
async def logout(request: Request, current_user: User = Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(token_version=User.token_version + 1)
        )
        log = OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="logout",
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        session.add(log)
        await session.commit()

    return success_response(data=None, message="已退出登录")
