"""
Unit tests for OSS adapter (app/adapters/oss.py).

覆盖：
- upload_file：成功、oss2 异常
- get_download_url：成功、失败
- delete_file：成功、失败
- _get_oss_credential：config 缺 bucket / endpoint 边界

Mock 策略：纯 mock，不真实调外部 OSS。
范式参考 tests/unit/services/test_tikhub_adapter.py。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.oss import (
    delete_file,
    get_download_url,
    upload_file,
    upload_file_from_path,
)


@pytest.fixture
def mock_db():
    """Mock AsyncSession：add 同步，commit 异步（适配 OSS adapter 写 OssCallLog 后 commit 的模式）。"""
    db = MagicMock()
    db.commit = AsyncMock()
    return db


# ── upload_file ──────────────────────────────────────────────────────


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_success(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """upload_file 成功：调用 put_object、写 report_success、返回 oss_key。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    # oss2 put_object 成功返回 RequestResult，status=200
    mock_to_thread.return_value = MagicMock(status=200, etag="abc")

    result = await upload_file("test/file.txt", b"hello", "text/plain", db=mock_db)

    assert result == "test/file.txt"
    # to_thread 应以 put_object 为第一参数被调用
    assert mock_to_thread.call_args.args[0] == bucket.put_object
    assert mock_to_thread.call_args.kwargs["headers"] == {
        "Content-Type": "text/plain",
        "x-oss-object-acl": "private",
    }
    mock_report_success.assert_awaited_once()
    mock_report_failure.assert_not_awaited()


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_failure(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """upload_file 失败：oss2 抛异常（generic Exception）→ report_failure + 包装为 RuntimeError 传播。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    # 模拟 oss2.exceptions.OssError（非 RuntimeError 子类，会被包装）
    mock_to_thread.side_effect = Exception("oss2 put_object failed")

    with pytest.raises(RuntimeError, match="OSS upload_file failed"):
        await upload_file("test/file.txt", b"hello", "text/plain", db=mock_db)

    mock_report_failure.assert_awaited_once()
    mock_report_success.assert_not_awaited()


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_from_path_streams_source_file_to_oss(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
    tmp_path,
):
    """路径上传必须调用 OSS 的文件接口，不能退回整份 bytes 上传。"""
    source = tmp_path / "large-video.mp4"
    source.write_bytes(b"video-content")
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    mock_to_thread.return_value = MagicMock(status=200, etag="abc")

    result = await upload_file_from_path(
        "test/large-video.mp4", source, "video/mp4", db=mock_db
    )

    assert result == "test/large-video.mp4"
    assert mock_to_thread.call_args.args[0] == bucket.put_object_from_file
    assert mock_to_thread.call_args.args[2] == str(source)
    bucket.put_object.assert_not_called()
    mock_report_success.assert_awaited_once()
    mock_report_failure.assert_not_awaited()


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_from_path_failure_keeps_upload_call_log(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
    tmp_path,
):
    """文件流上传失败仍要记录 OSS 调用，便于排查外部服务异常。"""
    from app.models.oss_call_log import OssCallLog

    source = tmp_path / "failed-video.mp4"
    source.write_bytes(b"video-content")
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.side_effect = OSError("network unavailable")

    with pytest.raises(RuntimeError, match="upload_file_from_path failed"):
        await upload_file_from_path("test/failed-video.mp4", source, "video/mp4", db=mock_db)

    logs = [call.args[0] for call in mock_db.add.call_args_list if isinstance(call.args[0], OssCallLog)]
    assert len(logs) == 1
    assert logs[0].operation == "upload"
    assert logs[0].status == "fail"
    assert "network unavailable" in (logs[0].error_message or "")
    mock_report_failure.assert_awaited_once()
    mock_report_success.assert_not_awaited()


# ── get_download_url ─────────────────────────────────────────────────


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_get_download_url_success(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """get_download_url 成功：调用 sign_url、写 report_success、返回 URL。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    mock_to_thread.return_value = "https://signed-url.example.com/file?token=abc"

    result = await get_download_url("test/file.txt", db=mock_db, expires=1800)

    assert result == "https://signed-url.example.com/file?token=abc"
    assert mock_to_thread.call_args.args[0] == bucket.sign_url
    mock_report_success.assert_awaited_once()
    mock_report_failure.assert_not_awaited()


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_get_download_url_failure(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """get_download_url 失败：sign_url 抛异常 → report_failure + 异常传播。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.side_effect = RuntimeError("sign_url failed")

    with pytest.raises(RuntimeError, match="sign_url failed"):
        await get_download_url("test/file.txt", db=mock_db)

    mock_report_failure.assert_awaited_once()
    mock_report_success.assert_not_awaited()


# ── delete_file ──────────────────────────────────────────────────────


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_delete_file_success(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """delete_file 成功：调用 delete_object、写 report_success。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    mock_to_thread.return_value = MagicMock(status=204)

    await delete_file("test/file.txt", db=mock_db)

    assert mock_to_thread.call_args.args[0] == bucket.delete_object
    mock_report_success.assert_awaited_once()
    mock_report_failure.assert_not_awaited()


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_delete_file_failure(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """delete_file 失败：delete_object 抛异常 → report_failure + 异常传播。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.side_effect = RuntimeError("delete_object failed")

    with pytest.raises(RuntimeError, match="delete_object failed"):
        await delete_file("test/file.txt", db=mock_db)

    mock_report_failure.assert_awaited_once()
    mock_report_success.assert_not_awaited()


# ── _get_oss_credential 边界 ─────────────────────────────────────────


@patch("app.adapters.oss.pick_credential", new_callable=AsyncMock)
async def test_get_credential_missing_bucket_raises(mock_pick, mock_db):
    """config 缺 bucket：KeyError 直接传播，不在 try 内（无法 report_failure）。"""
    from app.adapters.oss import _get_oss_credential

    cred = MagicMock()
    cred.id = 42
    cred.label = "AKIDxxx"
    cred.secret_enc = "SECRETxxx"
    cred.config = {"endpoint": "oss-cn-hangzhou.aliyuncs.com"}  # 没有 bucket
    mock_pick.return_value = cred

    with pytest.raises(KeyError, match="bucket"):
        await _get_oss_credential(db=mock_db)


@patch("app.adapters.oss.pick_credential", new_callable=AsyncMock)
async def test_get_credential_missing_endpoint_raises(mock_pick, mock_db):
    """config 缺 endpoint：KeyError 直接传播。"""
    from app.adapters.oss import _get_oss_credential

    cred = MagicMock()
    cred.id = 42
    cred.label = "杭州生产"
    cred.secret_enc = "SECRETxxx"
    cred.config = {"bucket": "my-bucket", "access_key_id": "AKIDxxx"}  # 没有 endpoint
    mock_pick.return_value = cred

    with pytest.raises(KeyError, match="endpoint"):
        await _get_oss_credential(db=mock_db)


@patch("app.adapters.oss.pick_credential", new_callable=AsyncMock)
async def test_get_credential_missing_access_key_id_raises(mock_pick, mock_db):
    """config 缺 access_key_id：KeyError 直接传播。"""
    from app.adapters.oss import _get_oss_credential

    cred = MagicMock()
    cred.id = 42
    cred.label = "杭州生产"
    cred.secret_enc = "SECRETxxx"
    cred.config = {
        "bucket": "my-bucket",
        "endpoint": "oss-cn-hangzhou.aliyuncs.com",
        # 没有 access_key_id
    }
    mock_pick.return_value = cred

    with pytest.raises(KeyError, match="access_key_id"):
        await _get_oss_credential(db=mock_db)


# ── OssCallLog 写入测试 ─────────────────────────────────────────────


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_writes_call_log_success(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """upload_file 成功：finally 块写 OssCallLog，operation=upload, status=success。"""
    from app.adapters.oss import upload_file
    from app.models.oss_call_log import OssCallLog

    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.return_value = MagicMock(status=200, etag="abc")

    await upload_file("test/file.txt", b"hello", "text/plain", db=mock_db, user_id=7)

    # mock_db.add 应被调用过，且参数是 OssCallLog 实例
    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    oss_log_calls = [c for c in add_calls if isinstance(c, OssCallLog)]
    assert len(oss_log_calls) == 1
    log = oss_log_calls[0]
    assert log.credential_id == 42
    assert log.user_id == 7
    assert log.operation == "upload"
    assert log.status == "success"
    assert log.oss_key == "test/file.txt"
    assert log.error_message is None
    assert isinstance(log.latency_ms, int)
    # finally 块触发 commit
    mock_db.commit.assert_awaited()


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_writes_call_log_failure(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """upload_file 失败：finally 块写 OssCallLog，status=fail + error_message。"""
    from app.adapters.oss import upload_file
    from app.models.oss_call_log import OssCallLog

    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.side_effect = Exception("network timeout")

    with pytest.raises(RuntimeError):
        await upload_file("test/file.txt", b"hello", "text/plain", db=mock_db, user_id=7)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    oss_log_calls = [c for c in add_calls if isinstance(c, OssCallLog)]
    assert len(oss_log_calls) == 1
    log = oss_log_calls[0]
    assert log.operation == "upload"
    assert log.status == "fail"
    assert "network timeout" in (log.error_message or "")


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_delete_file_writes_call_log(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """delete_file 成功：finally 块写 OssCallLog，operation=delete。"""
    from app.adapters.oss import delete_file
    from app.models.oss_call_log import OssCallLog

    mock_get_cred.return_value = (99, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.return_value = MagicMock(status=204)

    await delete_file("test/file.txt", db=mock_db, user_id=3)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    oss_log_calls = [c for c in add_calls if isinstance(c, OssCallLog)]
    assert len(oss_log_calls) == 1
    log = oss_log_calls[0]
    assert log.credential_id == 99
    assert log.user_id == 3
    assert log.operation == "delete"
    assert log.status == "success"


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_get_download_url_writes_call_log(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """get_download_url 成功：finally 块写 OssCallLog，operation=download。"""
    from app.adapters.oss import get_download_url
    from app.models.oss_call_log import OssCallLog

    mock_get_cred.return_value = (55, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.return_value = "https://signed.example.com/file?token=abc"

    await get_download_url("test/file.txt", db=mock_db, user_id=12)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    oss_log_calls = [c for c in add_calls if isinstance(c, OssCallLog)]
    assert len(oss_log_calls) == 1
    log = oss_log_calls[0]
    assert log.credential_id == 55
    assert log.user_id == 12
    assert log.operation == "download"
    assert log.status == "success"


@patch("app.adapters.oss.report_success", new_callable=AsyncMock)
@patch("app.adapters.oss.report_failure", new_callable=AsyncMock)
@patch("app.adapters.oss.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.oss._make_bucket")
@patch("app.adapters.oss._get_oss_credential", new_callable=AsyncMock)
async def test_upload_file_no_user_id(
    mock_get_cred,
    mock_make_bucket,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """upload_file 未传 user_id：日志 user_id=None，不报错。"""
    from app.adapters.oss import upload_file
    from app.models.oss_call_log import OssCallLog

    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.return_value = MagicMock(status=200, etag="abc")

    await upload_file("test/file.txt", b"hello", "text/plain", db=mock_db)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    oss_log_calls = [c for c in add_calls if isinstance(c, OssCallLog)]
    assert len(oss_log_calls) == 1
    assert oss_log_calls[0].user_id is None
