"""
app/adapters/oss.py

阿里云 OSS 适配器：上传 / 下载 URL / 删除。

凭证配置来自 service_credentials 表（provider="oss"），
config JSONB 字段结构：
{
    "access_key_id": "LTAI...",                 # AccessKey ID
    "bucket": "your-bucket-name",
    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
    "region": "cn-hangzhou"                      # 可选
}

字段映射（与通用凭证管理 API `/api/admin/config/credentials` 约定一致）：
- label = 备注名（人类可读，如 "杭州生产环境"，管理员自定义）
- secret_enc = AccessKey Secret（Sprint 3 阶段明文）
- config.access_key_id = AccessKey ID
- config.bucket / endpoint / region = OSS 元数据
"""
import asyncio
import time

import oss2
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oss_call_log import OssCallLog
from app.services.credential_selector import (
    pick_credential,
    report_failure,
    report_success,
)


def _make_bucket(
    access_key_id: str,
    access_key_secret: str,
    endpoint: str,
    bucket_name: str,
) -> oss2.Bucket:
    """构造 oss2.Bucket 实例（工厂函数，便于单元测试 mock）。"""
    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)


async def _get_oss_credential(
    db: AsyncSession,
) -> tuple[int, str, str, str, str]:
    """
    返回 (cred_id, access_key_id, access_key_secret, bucket, endpoint)。

    注意：本函数在 try 块**外**调用 —— 凭证缺失 / config 缺字段时
    直接抛 KeyError，无法 report_failure（因为还没拿到 cred_id，
    也不应把"凭证配置错误"当作 oss2 调用失败累计）。
    """
    credential = await pick_credential(provider="oss", db=db)
    config = credential.config or {}
    bucket = config["bucket"]
    endpoint = config["endpoint"]
    access_key_id = config["access_key_id"]
    return (
        credential.id,
        access_key_id,
        credential.secret_enc,
        bucket,
        endpoint,
    )


async def upload_file(
    oss_key: str,
    content: bytes,
    content_type: str,
    db: AsyncSession,
    user_id: int | None = None,
) -> str:
    """
    上传文件到 OSS。

    Args:
        oss_key: OSS 对象键（如 "test/file.txt"）
        content: 文件二进制内容
        content_type: MIME 类型（如 "text/plain" / "image/png"）
        db: 数据库会话
        user_id: 调用方用户 ID（写入 oss_call_logs，用于统计）

    Returns:
        oss_key（成功时返回输入的 oss_key）

    Raises:
        KeyError: 凭证 config 缺 bucket / endpoint
        RuntimeError: OSS 上传失败
    """
    cred_id, ak_id, ak_secret, bucket_name, endpoint = await _get_oss_credential(db)
    start = time.monotonic()
    status = "success"
    error_message: str | None = None
    try:
        bucket = _make_bucket(ak_id, ak_secret, endpoint, bucket_name)
        result = await asyncio.to_thread(
            bucket.put_object,
            oss_key,
            content,
            headers={
                "Content-Type": content_type,
                "x-oss-object-acl": oss2.OBJECT_ACL_PRIVATE,
            },
        )
        if result.status != 200:
            raise RuntimeError(f"OSS put_object non-200 status={result.status}")
        await report_success(cred_id, db)
        return oss_key
    except Exception as e:
        status = "fail"
        error_message = str(e)[:500]
        await report_failure(cred_id, db)
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"OSS upload_file failed: {e}") from e
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        db.add(OssCallLog(
            credential_id=cred_id,
            user_id=user_id,
            operation="upload",
            status=status,
            latency_ms=latency_ms,
            oss_key=oss_key,
            error_message=error_message,
        ))
        await db.commit()


async def get_download_url(
    oss_key: str,
    db: AsyncSession,
    expires: int = 3600,
    user_id: int | None = None,
) -> str:
    """
    生成 OSS 文件临时下载 URL（默认 1 小时有效）。

    Args:
        oss_key: OSS 对象键
        db: 数据库会话
        expires: URL 有效期（秒）
        user_id: 调用方用户 ID（写入 oss_call_logs，用于统计）

    Returns:
        签名后的下载 URL

    Raises:
        KeyError: 凭证 config 缺 bucket / endpoint
        RuntimeError: 生成 URL 失败
    """
    cred_id, ak_id, ak_secret, bucket_name, endpoint = await _get_oss_credential(db)
    start = time.monotonic()
    status = "success"
    error_message: str | None = None
    try:
        bucket = _make_bucket(ak_id, ak_secret, endpoint, bucket_name)
        url = await asyncio.to_thread(
            bucket.sign_url,
            "GET",
            oss_key,
            expires,
        )
        await report_success(cred_id, db)
        return url
    except Exception as e:
        status = "fail"
        error_message = str(e)[:500]
        await report_failure(cred_id, db)
        raise RuntimeError(f"OSS get_download_url failed: {e}") from e
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        db.add(OssCallLog(
            credential_id=cred_id,
            user_id=user_id,
            operation="download",
            status=status,
            latency_ms=latency_ms,
            oss_key=oss_key,
            error_message=error_message,
        ))
        await db.commit()


async def delete_file(
    oss_key: str,
    db: AsyncSession,
    user_id: int | None = None,
) -> None:
    """
    删除 OSS 文件。

    Args:
        oss_key: OSS 对象键
        db: 数据库会话
        user_id: 调用方用户 ID（写入 oss_call_logs，用于统计）

    Raises:
        KeyError: 凭证 config 缺 bucket / endpoint
        RuntimeError: 删除失败
    """
    cred_id, ak_id, ak_secret, bucket_name, endpoint = await _get_oss_credential(db)
    start = time.monotonic()
    status = "success"
    error_message: str | None = None
    try:
        bucket = _make_bucket(ak_id, ak_secret, endpoint, bucket_name)
        await asyncio.to_thread(bucket.delete_object, oss_key)
        await report_success(cred_id, db)
    except Exception as e:
        status = "fail"
        error_message = str(e)[:500]
        await report_failure(cred_id, db)
        raise RuntimeError(f"OSS delete_file failed: {e}") from e
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        db.add(OssCallLog(
            credential_id=cred_id,
            user_id=user_id,
            operation="delete",
            status=status,
            latency_ms=latency_ms,
            oss_key=oss_key,
            error_message=error_message,
        ))
        await db.commit()
