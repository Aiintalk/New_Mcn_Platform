"""
app/adapters/oss.py

阿里云 OSS 适配器（M1 阶段：结构预留，真实调用待 OSS 凭证就绪后实现）

凭证配置来自 service_credentials 表（provider="oss"），
config JSONB 字段结构：
{
    "bucket": "your-bucket-name",
    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
    "region": "cn-hangzhou"
}
secret_enc 存储 access_key_secret（加密）；label 中填写 access_key_id
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.credential_selector import pick_credential  # noqa: F401 — reserved for real impl


async def get_download_url(oss_key: str, db: AsyncSession, expires: int = 3600) -> str:
    """
    生成 OSS 文件临时下载 URL。

    当前返回 Mock URL；真实实现需要：
    1. pick_credential(provider="oss")
    2. oss2.Auth(access_key_id, access_key_secret)
    3. bucket.sign_url('GET', oss_key, expires)

    TODO: 阿里云凭证就绪后替换 Mock 实现
    """
    return f"https://mock-oss.example.com/{oss_key}?token=mock&expires={expires}"


async def upload_file(
    oss_key: str,
    content: bytes,
    content_type: str,
    db: AsyncSession,
) -> str:
    """
    上传文件到 OSS，返回 oss_key。
    TODO: 真实实现待凭证就绪
    """
    raise NotImplementedError("OSS upload not implemented yet - waiting for credentials")
