import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter(prefix="/admin/users")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_PAGE_SIZE_ALLOWED = {10, 20, 50}
_DEFAULT_PASSWORD = "Mcn@123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "real_name": u.real_name,
        "role": u.role,
        "status": u.status,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "last_active_at": u.last_active_at.isoformat() if u.last_active_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


async def _write_op_log(
    session,
    actor: User,
    action: str,
    request: Request,
    target_type: str | None = "user",
    target_id: int | None = None,
    detail: dict | None = None,
) -> None:
    log = OperationLog(
        user_id=actor.id,
        username=actor.username,
        role=actor.role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    session.add(log)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str
    real_name: str
    role: str = "operator"
    password: str | None = None  # 不传则使用默认值 Mcn@123


class UpdateUserRequest(BaseModel):
    real_name: str | None = None
    role: str | None = None
    status: str | None = None


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------

@router.get("", response_model=ApiResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    status: str = "",
    role: str = "",
    current_user: User = Depends(require_admin),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(User).where(User.deleted_at.is_(None))
        if keyword:
            q = q.where(
                (User.username.ilike(f"%{keyword}%")) | (User.real_name.ilike(f"%{keyword}%"))
            )
        if status:
            q = q.where(User.status == status)
        if role:
            q = q.where(User.role == role)

        total_result = await session.execute(
            select(User.id).where(User.deleted_at.is_(None))
            .where(*([] if not keyword else [
                (User.username.ilike(f"%{keyword}%")) | (User.real_name.ilike(f"%{keyword}%"))
            ]))
        )
        # simpler count approach
        count_q = select(User).where(User.deleted_at.is_(None))
        if keyword:
            count_q = count_q.where(
                (User.username.ilike(f"%{keyword}%")) | (User.real_name.ilike(f"%{keyword}%"))
            )
        if status:
            count_q = count_q.where(User.status == status)
        if role:
            count_q = count_q.where(User.role == role)

        all_rows = (await session.execute(count_q)).scalars().all()
        total = len(all_rows)

        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await session.execute(q)).scalars().all()

    import math
    total_pages = math.ceil(total / page_size) if page_size else 1

    return success_response(
        data={
            "items": [_user_to_dict(u) for u in rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }
    )


# ---------------------------------------------------------------------------
# GET /api/admin/users/check-username?username=xxx
# 必须在 /{user_id} 之前声明
# ---------------------------------------------------------------------------

@router.get("/check-username", response_model=ApiResponse)
async def check_username(
    username: str = "",
    current_user: User = Depends(require_admin),
):
    """
    检测用户名是否可用。
    - available=True：可直接使用
    - available=False：已存在，suggested 为可用的建议值（username1, username2, ...）
    """
    if not username:
        return error_response(ErrorCode.VALIDATION_ERROR, "username 不能为空")

    async with AsyncSessionLocal() as session:
        exists = (await session.execute(
            select(User.id).where(User.username == username, User.deleted_at.is_(None))
        )).scalar_one_or_none()

        if not exists:
            return success_response(data={"available": True, "suggested": None})

        # 找可用的建议值：username1, username2, ...
        suggested = None
        for i in range(1, 100):
            candidate = f"{username}{i}"
            taken = (await session.execute(
                select(User.id).where(User.username == candidate, User.deleted_at.is_(None))
            )).scalar_one_or_none()
            if not taken:
                suggested = candidate
                break

    return success_response(data={"available": False, "suggested": suggested})


# ---------------------------------------------------------------------------
# POST /api/admin/users
# ---------------------------------------------------------------------------

@router.post("", response_model=ApiResponse)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    plain_pw = body.password if body.password else _DEFAULT_PASSWORD

    async with AsyncSessionLocal() as session:
        existing = (await session.execute(
            select(User).where(User.username == body.username, User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if existing:
            return error_response(ErrorCode.USERNAME_ALREADY_EXISTS, "用户名已存在")

        new_user = User(
            username=body.username,
            real_name=body.real_name,
            role=body.role,
            password_hash=pwd_context.hash(plain_pw),
            password_changed_at=None,
            created_by=current_user.id,
        )
        session.add(new_user)
        await session.flush()

        await _write_op_log(session, current_user, "create_user", request, target_id=new_user.id)
        await session.commit()
        await session.refresh(new_user)

    return success_response(
        data={
            "id": new_user.id,
            "username": new_user.username,
            "real_name": new_user.real_name,
            "role": new_user.role,
            "status": new_user.status,
            "initial_password": plain_pw,
        },
        message="账号创建成功",
    )


# ---------------------------------------------------------------------------
# GET /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

@router.get("/{user_id}", response_model=ApiResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()

    if not user:
        return error_response(ErrorCode.USER_NOT_FOUND, "用户不存在")

    return success_response(data=_user_to_dict(user))


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id}
# ---------------------------------------------------------------------------

@router.patch("/{user_id}", response_model=ApiResponse)
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not user:
            return error_response(ErrorCode.USER_NOT_FOUND, "用户不存在")

        values: dict = {}
        if body.real_name is not None:
            values["real_name"] = body.real_name
        if body.role is not None:
            values["role"] = body.role
        if body.status is not None:
            values["status"] = body.status

        if values:
            await session.execute(update(User).where(User.id == user_id).values(**values))

        await _write_op_log(
            session, current_user, "update_user", request,
            target_id=user_id, detail=values or None,
        )
        await session.commit()
        await session.refresh(user)

    return success_response(data=_user_to_dict(user))


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/reset-password
# ---------------------------------------------------------------------------

@router.post("/{user_id}/reset-password", response_model=ApiResponse)
async def reset_password(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not user:
            return error_response(ErrorCode.USER_NOT_FOUND, "用户不存在")

        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                password_hash=pwd_context.hash(_DEFAULT_PASSWORD),
                password_changed_at=None,          # 强制下次登录改密
                token_version=User.token_version + 1,  # 踢出所有已有 token
            )
        )
        await _write_op_log(session, current_user, "reset_password", request, target_id=user_id)
        await session.commit()

    return success_response(data={"initial_password": _DEFAULT_PASSWORD}, message="密码已重置")


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/enable
# ---------------------------------------------------------------------------

@router.post("/{user_id}/enable", response_model=ApiResponse)
async def enable_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not user:
            return error_response(ErrorCode.USER_NOT_FOUND, "用户不存在")

        await session.execute(update(User).where(User.id == user_id).values(status="enabled"))
        await _write_op_log(session, current_user, "enable_user", request, target_id=user_id)
        await session.commit()

    return success_response(data=None, message="用户已启用")


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/disable
# ---------------------------------------------------------------------------

@router.post("/{user_id}/disable", response_model=ApiResponse)
async def disable_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not user:
            return error_response(ErrorCode.USER_NOT_FOUND, "用户不存在")

        await session.execute(update(User).where(User.id == user_id).values(status="disabled"))
        await _write_op_log(session, current_user, "disable_user", request, target_id=user_id)
        await session.commit()

    return success_response(data=None, message="用户已停用")


# ---------------------------------------------------------------------------
# DELETE /api/admin/users/{user_id}   (soft delete)
# ---------------------------------------------------------------------------

@router.delete("/{user_id}", response_model=ApiResponse)
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(
                select(User).where(User.id == user_id, User.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not user:
            return error_response(ErrorCode.USER_NOT_FOUND, "用户不存在")

        if user.role == "admin":
            return error_response(ErrorCode.PERMISSION_DENIED, "不能删除管理员账号")

        now = datetime.now(tz=timezone.utc)
        await session.execute(
            update(User).where(User.id == user_id).values(deleted_at=now)
        )
        await _write_op_log(session, current_user, "delete_user", request, target_id=user_id)
        await session.commit()

    return success_response(data=None, message="用户已删除")
