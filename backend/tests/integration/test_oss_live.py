"""
Live integration test for OSS adapter (真实阿里云 OSS 连通性验证).

前置条件（用户配置）：
1. 在 mcn_test 数据库的 service_credentials 表插入 OSS 凭证：
   ```sql
   INSERT INTO service_credentials (provider, label, secret_enc, status, weight, config)
   VALUES ('oss', '<AccessKeyID>', '<AccessKeySecret>', 'enabled', 1,
           '{"bucket":"<bucket-name>","endpoint":"oss-cn-hangzhou.aliyuncs.com","region":"cn-hangzhou"}');
   ```
2. 设置环境变量 `OSS_LIVE_TEST=1` 启用测试（默认跳过）
3. 阿里云 OSS Bucket 已创建，且 AccessKey 有读写权限

运行方式：
```bash
OSS_LIVE_TEST=1 .venv311/Scripts/python -m pytest tests/integration/test_oss_live.py -v -m live --override-ini="addopts="
```

注意：
- 本测试在 backend/tests/integration/ 下（非 routers/ 子目录），不会被 test_convention_guard.py 扫描
- 测试用 test_session fixture（mcn_test 库），所以凭证要配在 mcn_test
- 上传的对象在 finally 中删除，确保不留垃圾
"""
import os
import uuid

import httpx
import pytest

from app.adapters.oss import delete_file, get_download_url, upload_file


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.getenv("OSS_LIVE_TEST"),
        reason=(
            "Set OSS_LIVE_TEST=1 to run live OSS tests. "
            "Requires real Aliyun OSS credential in service_credentials table of mcn_test DB."
        ),
    ),
]


@pytest.mark.live
async def test_oss_upload_download_delete_round_trip(test_session):
    """端到端：upload → download → 验证内容 → delete（round-trip）。"""
    oss_key = f"test/oss-live-{uuid.uuid4().hex[:8]}.txt"
    content = f"hello oss live test {uuid.uuid4().hex}".encode("utf-8")

    # 1. upload
    returned_key = await upload_file(oss_key, content, "text/plain", db=test_session)
    assert returned_key == oss_key, "upload_file 应返回传入的 oss_key"

    try:
        # 2. download via signed URL → 内容一致
        url = await get_download_url(oss_key, db=test_session)
        assert "OSSAccessKeyId" in url or "Signature" in url, f"URL 应是签名 URL: {url}"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
        assert resp.status_code == 200, f"GET 签名 URL 失败: {resp.status_code} {resp.text[:200]}"
        assert resp.content == content, "下载内容应与上传内容一致"
    finally:
        # 3. cleanup: delete（无论上面断言是否失败都尝试删除）
        try:
            await delete_file(oss_key, db=test_session)
        except Exception:
            pass  # best-effort cleanup；测试失败时已经抛在上面了
