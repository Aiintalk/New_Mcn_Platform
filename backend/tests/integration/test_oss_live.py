"""
Live integration test for OSS adapter (真实阿里云 OSS 连通性验证).

前置条件（用户配置）：
1. 阿里云准备：RAM 子用户 + AccessKey ID/Secret + OSS Bucket
2. 设置环境变量：
   - OSS_LIVE_TEST=1（启用测试，否则默认跳过）
   - OSS_ACCESS_KEY_ID（24 位，LTAI 开头）
   - OSS_ACCESS_KEY_SECRET（30 位）
   - OSS_BUCKET（Bucket 名）
   - OSS_ENDPOINT（选填，默认 oss-cn-hangzhou.aliyuncs.com）
   - OSS_REGION（选填，默认 cn-hangzhou）

设计说明：
- 测试用 test_session（mcn_test 库），凭证在测试内动态 INSERT
- conftest 的 test_engine 在 session 结束时 drop_all，凭证自然清理
- 上传的 OSS 对象在 finally 中删除，不留垃圾
- Secret 只通过 env var 传入，不写进代码 / 不写进 git
- 本测试在 backend/tests/integration/ 下（非 routers/ 子目录），不被 test_convention_guard.py 扫描

运行方式（Windows bash）：
```bash
OSS_LIVE_TEST=1 OSS_ACCESS_KEY_ID=xxx OSS_ACCESS_KEY_SECRET=xxx OSS_BUCKET=xxx \\
  .venv311/Scripts/python -m pytest tests/integration/test_oss_live.py -v -m live --override-ini="addopts="
```
"""
import os
import uuid

import httpx
import pytest

from app.adapters.oss import delete_file, get_download_url, upload_file
from app.models.credential import ServiceCredential


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.getenv("OSS_LIVE_TEST"),
        reason=(
            "Set OSS_LIVE_TEST=1 to run live OSS tests. "
            "Also requires OSS_ACCESS_KEY_ID/SECRET/BUCKET env vars."
        ),
    ),
]


def _get_oss_config_from_env() -> dict | None:
    """从环境变量读 OSS 配置，缺关键字段则返回 None。"""
    ak_id = os.getenv("OSS_ACCESS_KEY_ID")
    ak_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    bucket = os.getenv("OSS_BUCKET")
    if not (ak_id and ak_secret and bucket):
        return None
    return {
        "access_key_id": ak_id,
        "access_key_secret": ak_secret,
        "bucket": bucket,
        "endpoint": os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com"),
        "region": os.getenv("OSS_REGION", "cn-hangzhou"),
    }


async def _setup_oss_credential(test_session, cfg: dict) -> None:
    """在 test_session 里插入 OSS 凭证（test_engine 结束时 drop 整库，自动清理）。"""
    cred = ServiceCredential(
        provider="oss",
        label="live-test",
        secret_enc=cfg["access_key_secret"],
        secret_tail=cfg["access_key_secret"][-4:],
        status="enabled",
        weight=10,
        config={
            "access_key_id": cfg["access_key_id"],
            "bucket": cfg["bucket"],
            "endpoint": cfg["endpoint"],
            "region": cfg["region"],
        },
    )
    test_session.add(cred)
    await test_session.commit()


@pytest.mark.live
async def test_oss_upload_download_delete_round_trip(test_session):
    """端到端：upload → download → 验证内容 → delete（round-trip）。"""
    cfg = _get_oss_config_from_env()
    if cfg is None:
        pytest.fail(
            "OSS_LIVE_TEST=1 已设但缺少 OSS_ACCESS_KEY_ID/SECRET/BUCKET 环境变量。"
            "请补齐后再跑（Secret 通过 env 传入，不要写进代码）。"
        )

    # 1. 在 test_session 插入 OSS 凭证（mcn_test 库，conftest 已建表）
    await _setup_oss_credential(test_session, cfg)

    oss_key = f"test/oss-live-{uuid.uuid4().hex[:8]}.txt"
    content = f"hello oss live test {uuid.uuid4().hex}".encode("utf-8")

    # 2. upload
    returned_key = await upload_file(oss_key, content, "text/plain", db=test_session)
    assert returned_key == oss_key, "upload_file 应返回传入的 oss_key"

    try:
        # 3. download via signed URL → 内容一致
        url = await get_download_url(oss_key, db=test_session)
        assert "OSSAccessKeyId" in url or "Signature" in url, f"URL 应是签名 URL: {url}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
        assert resp.status_code == 200, f"GET 签名 URL 失败: {resp.status_code} {resp.text[:200]}"
        assert resp.content == content, "下载内容应与上传内容一致"
    finally:
        # 4. cleanup: delete（无论上面断言是否失败都尝试删除）
        try:
            await delete_file(oss_key, db=test_session)
        except Exception:
            pass  # best-effort cleanup；测试失败时已经抛在上面了
