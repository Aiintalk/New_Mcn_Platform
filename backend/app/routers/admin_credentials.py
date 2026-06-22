import asyncio
import math
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, select, update

from app.adapters.oss import _make_bucket
from app.adapters.asr import _make_client as _make_asr_client, _build_query_request as _build_asr_query_request
from app.core.database import AsyncSessionLocal
from app.core.response import ApiResponse, ErrorCode, error_response, success_response
from app.middlewares.auth import require_admin
from app.models.credential import ServiceCredential
from app.models.log import OperationLog
from app.models.user import User

router = APIRouter()

_PAGE_SIZE_ALLOWED = {10, 20, 50}


def _ts(dt) -> str | None:
    return dt.isoformat() if dt else None


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cred_to_dict(c: ServiceCredential) -> dict:
    """Never return secret_enc — only secret_tail."""
    return {
        "id": c.id,
        "provider": c.provider,
        "label": c.label,
        "secret_tail": c.secret_tail,
        "status": c.status,
        "weight": c.weight,
        "quota_limit": c.quota_limit,
        "quota_used": c.quota_used,
        "fail_count": c.fail_count,
        "cooldown_until": _ts(c.cooldown_until),
        "config": c.config,
        "created_at": _ts(c.created_at),
    }


def _pagination(total: int, page: int, page_size: int) -> dict:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if page_size else 1,
    }


class CreateCredentialRequest(BaseModel):
    provider: str
    label: str
    api_key: str
    weight: int = 1
    quota_limit: int | None = None
    config: dict | None = None


class UpdateCredentialRequest(BaseModel):
    label: str | None = None
    status: str | None = None
    weight: int | None = None
    quota_limit: int | None = None
    config: dict | None = None
    api_key: str | None = None  # 提供则同步轮换 secret_enc + secret_tail


# ---------------------------------------------------------------------------
# GET /api/admin/config/credentials
# ---------------------------------------------------------------------------

@router.get("/admin/config/credentials", response_model=ApiResponse)
async def list_credentials(
    provider: str = "",
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_admin),
):
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    async with AsyncSessionLocal() as session:
        q = select(ServiceCredential)
        if provider:
            q = q.where(ServiceCredential.provider == provider)
        q = q.order_by(ServiceCredential.provider.asc(), ServiceCredential.created_at.asc())

        total = len((await session.execute(q)).scalars().all())
        rows = (await session.execute(
            q.offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()

    return success_response(data={
        "items": [_cred_to_dict(c) for c in rows],
        "pagination": _pagination(total, page, page_size),
    })


# ---------------------------------------------------------------------------
# POST /api/admin/config/credentials
# ---------------------------------------------------------------------------

@router.post("/admin/config/credentials", response_model=ApiResponse)
async def create_credential(
    body: CreateCredentialRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    secret_enc = body.api_key  # Sprint 3: store plaintext; encryption added in Sprint 4
    secret_tail = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key

    async with AsyncSessionLocal() as session:
        cred = ServiceCredential(
            provider=body.provider,
            label=body.label,
            secret_enc=secret_enc,
            secret_tail=secret_tail,
            weight=body.weight,
            quota_limit=body.quota_limit,
            config=body.config,
            created_by=current_user.id,
        )
        session.add(cred)
        await session.flush()

        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="create_credential",
            target_type="credential",
            target_id=cred.id,
            detail={"provider": body.provider, "label": body.label},
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(cred)

    return success_response(data=_cred_to_dict(cred), message="密钥创建成功")


# ---------------------------------------------------------------------------
# PATCH /api/admin/config/credentials/{credential_id}
# ---------------------------------------------------------------------------

@router.patch("/admin/config/credentials/{credential_id}", response_model=ApiResponse)
async def update_credential(
    credential_id: int,
    body: UpdateCredentialRequest,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()

        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")

        values: dict = {}
        if body.label is not None:
            values["label"] = body.label
        if body.status is not None:
            values["status"] = body.status
        if body.weight is not None:
            values["weight"] = body.weight
        if body.quota_limit is not None:
            values["quota_limit"] = body.quota_limit
        if body.config is not None:
            values["config"] = body.config
        if body.api_key is not None:
            values["secret_enc"] = body.api_key
            values["secret_tail"] = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key

        if values:
            await session.execute(
                update(ServiceCredential)
                .where(ServiceCredential.id == credential_id)
                .values(**values)
            )

        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="update_credential",
            target_type="credential",
            target_id=credential_id,
            detail=values or None,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(cred)

    return success_response(data=_cred_to_dict(cred))


# ---------------------------------------------------------------------------
# DELETE /api/admin/config/credentials/{credential_id}  (physical delete)
# ---------------------------------------------------------------------------

@router.delete("/admin/config/credentials/{credential_id}", response_model=ApiResponse)
async def delete_credential(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()

        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")

        await session.execute(
            delete(ServiceCredential).where(ServiceCredential.id == credential_id)
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="delete_credential",
            target_type="credential",
            target_id=credential_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()

    return success_response(data=None, message="密钥已删除")


# ---------------------------------------------------------------------------
# POST /api/admin/config/credentials/{credential_id}/enable
# POST /api/admin/config/credentials/{credential_id}/disable
# ---------------------------------------------------------------------------

@router.post("/admin/config/credentials/{credential_id}/enable", response_model=ApiResponse)
async def enable_credential(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()
        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")

        await session.execute(
            update(ServiceCredential)
            .where(ServiceCredential.id == credential_id)
            .values(status="enabled")
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="enable_credential",
            target_type="credential",
            target_id=credential_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(cred)

    return success_response(data=_cred_to_dict(cred), message="密钥已启用")


@router.post("/admin/config/credentials/{credential_id}/disable", response_model=ApiResponse)
async def disable_credential(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()
        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")

        await session.execute(
            update(ServiceCredential)
            .where(ServiceCredential.id == credential_id)
            .values(status="disabled")
        )
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="disable_credential",
            target_type="credential",
            target_id=credential_id,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()
        await session.refresh(cred)

    return success_response(data=_cred_to_dict(cred), message="密钥已停用")


# ---------------------------------------------------------------------------
# POST /api/admin/config/credentials/{credential_id}/test — 测试连通性（当前仅 OSS）
# ---------------------------------------------------------------------------

async def _record_test_outcome(
    credential_id: int,
    current_user: User,
    request: Request,
    status: str,
    latency_ms: int,
    provider: str,
    error_msg: str = "",
):
    """共用：测试完成后写 service_credentials.last_tested_at + OperationLog。"""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ServiceCredential)
            .where(ServiceCredential.id == credential_id)
            .values(last_tested_at=datetime.now(timezone.utc), last_latency_ms=latency_ms)
        )
        detail = {"status": status, "latency_ms": latency_ms, "provider": provider}
        if error_msg:
            detail["error"] = error_msg
        session.add(OperationLog(
            user_id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            action="test_credential",
            target_type="credential",
            target_id=credential_id,
            detail=detail,
            ip=_get_ip(request),
            user_agent=request.headers.get("user-agent"),
        ))
        await session.commit()


@router.post("/admin/config/credentials/{credential_id}/test", response_model=ApiResponse)
async def test_credential(
    credential_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
):
    """
    测试凭证连通性（OSS / ASR）。

    OSS：调 bucket.get_bucket_info（轻量）。
    ASR：调 GetTaskResult 用测试 TaskId（必返回业务错误如 41050010，
         但只要不抛认证/签名异常，就认为连通性 OK）。

    响应 data 结构（业务失败也走 success 信封，状态在 data.status）：
      OSS 成功：{"status": "ok", "latency_ms": 123, "bucket": "...", "location": "...", "creation_date": "..."}
      ASR 成功：{"status": "ok", "latency_ms": 123, "status_text": "...", "status_code": ...}
      失败：    {"status": "error", "latency_ms": 123, "error": "..."}
    """
    import json as _json

    async with AsyncSessionLocal() as session:
        cred = (await session.execute(
            select(ServiceCredential).where(ServiceCredential.id == credential_id)
        )).scalar_one_or_none()
        if cred is None:
            return error_response(ErrorCode.RESOURCE_NOT_FOUND, "密钥不存在")

        if cred.provider not in ("oss", "asr"):
            return error_response(
                ErrorCode.VALIDATION_ERROR,
                f"测试接口仅支持 OSS/ASR 凭证，got provider={cred.provider}",
            )

        # 解析凭证字段（在 session 内取，在 session 外调用）
        config = cred.config or {}
        provider = cred.provider
        secret_enc = cred.secret_enc or ""

        if provider == "oss":
            access_key_id = config.get("access_key_id")
            bucket_name = config.get("bucket")
            endpoint = config.get("endpoint")
            if not (access_key_id and bucket_name and endpoint):
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "OSS 凭证 config 缺少 access_key_id/bucket/endpoint",
                )
            access_key_secret = secret_enc
            oss_params = (access_key_id, access_key_secret, endpoint, bucket_name)
        else:  # asr
            app_key = config.get("app_key")
            if not app_key:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "ASR 凭证 config 缺少 app_key",
                )
            parts = secret_enc.split("\n", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                return error_response(
                    ErrorCode.VALIDATION_ERROR,
                    "ASR secret_enc 格式错误（需 'access_key_id\\naccess_key_secret'）",
                )
            region = config.get("region", "cn-shanghai")
            asr_params = (parts[0], parts[1], region)

    # 外部调用（在 DB session 外，避免阻塞连接池）
    start = time.monotonic()
    try:
        if provider == "oss":
            ak_id, ak_secret, endpoint, bucket_name = oss_params
            bucket = _make_bucket(ak_id, ak_secret, endpoint, bucket_name)
            info = await asyncio.to_thread(bucket.get_bucket_info)
            latency_ms = int((time.monotonic() - start) * 1000)
            await _record_test_outcome(
                credential_id, current_user, request,
                status="ok", latency_ms=latency_ms, provider="oss",
            )
            return success_response(data={
                "status": "ok",
                "latency_ms": latency_ms,
                "bucket": info.name,
                "location": info.location,
                "creation_date": info.creation_date,
            })
        else:  # asr
            ak_id, ak_secret, region = asr_params
            client = _make_asr_client(ak_id, ak_secret, region)
            # 用一个固定测试 TaskId 调 GetTaskResult
            # 预期返回业务错误（如 41050010 TASK_EXPIRED），但不抛认证异常
            req = _build_asr_query_request("test-connectivity-probe-task-id")
            resp_bytes = await asyncio.to_thread(client.do_action_with_exception, req)
            parsed = _json.loads(resp_bytes)
            latency_ms = int((time.monotonic() - start) * 1000)
            await _record_test_outcome(
                credential_id, current_user, request,
                status="ok", latency_ms=latency_ms, provider="asr",
            )
            return success_response(data={
                "status": "ok",
                "latency_ms": latency_ms,
                "status_text": parsed.get("StatusText", ""),
                "status_code": parsed.get("StatusCode"),
            })
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        err_msg = str(e)[:200]
        await _record_test_outcome(
            credential_id, current_user, request,
            status="error", latency_ms=latency_ms, provider=provider, error_msg=err_msg,
        )
        return success_response(data={
            "status": "error",
            "latency_ms": latency_ms,
            "error": err_msg,
        })
