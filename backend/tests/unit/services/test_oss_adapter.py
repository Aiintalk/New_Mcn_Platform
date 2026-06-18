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
)


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
):
    """upload_file 成功：调用 put_object、写 report_success、返回 oss_key。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    # oss2 put_object 成功返回 RequestResult，status=200
    mock_to_thread.return_value = MagicMock(status=200, etag="abc")

    result = await upload_file("test/file.txt", b"hello", "text/plain", db=MagicMock())

    assert result == "test/file.txt"
    # to_thread 应以 put_object 为第一参数被调用
    assert mock_to_thread.call_args.args[0] == bucket.put_object
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
):
    """upload_file 失败：oss2 抛异常（generic Exception）→ report_failure + 包装为 RuntimeError 传播。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    # 模拟 oss2.exceptions.OssError（非 RuntimeError 子类，会被包装）
    mock_to_thread.side_effect = Exception("oss2 put_object failed")

    with pytest.raises(RuntimeError, match="OSS upload_file failed"):
        await upload_file("test/file.txt", b"hello", "text/plain", db=MagicMock())

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
):
    """get_download_url 成功：调用 sign_url、写 report_success、返回 URL。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    mock_to_thread.return_value = "https://signed-url.example.com/file?token=abc"

    result = await get_download_url("test/file.txt", db=MagicMock(), expires=1800)

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
):
    """get_download_url 失败：sign_url 抛异常 → report_failure + 异常传播。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.side_effect = RuntimeError("sign_url failed")

    with pytest.raises(RuntimeError, match="sign_url failed"):
        await get_download_url("test/file.txt", db=MagicMock())

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
):
    """delete_file 成功：调用 delete_object、写 report_success。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    bucket = MagicMock()
    mock_make_bucket.return_value = bucket
    mock_to_thread.return_value = MagicMock(status=204)

    await delete_file("test/file.txt", db=MagicMock())

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
):
    """delete_file 失败：delete_object 抛异常 → report_failure + 异常传播。"""
    mock_get_cred.return_value = (42, "AKIDxxx", "SECRETxxx", "my-bucket", "oss-cn-hangzhou.aliyuncs.com")
    mock_make_bucket.return_value = MagicMock()
    mock_to_thread.side_effect = RuntimeError("delete_object failed")

    with pytest.raises(RuntimeError, match="delete_object failed"):
        await delete_file("test/file.txt", db=MagicMock())

    mock_report_failure.assert_awaited_once()
    mock_report_success.assert_not_awaited()


# ── _get_oss_credential 边界 ─────────────────────────────────────────


@patch("app.adapters.oss.pick_credential", new_callable=AsyncMock)
async def test_get_credential_missing_bucket_raises(mock_pick):
    """config 缺 bucket：KeyError 直接传播，不在 try 内（无法 report_failure）。"""
    from app.adapters.oss import _get_oss_credential

    cred = MagicMock()
    cred.id = 42
    cred.label = "AKIDxxx"
    cred.secret_enc = "SECRETxxx"
    cred.config = {"endpoint": "oss-cn-hangzhou.aliyuncs.com"}  # 没有 bucket
    mock_pick.return_value = cred

    with pytest.raises(KeyError, match="bucket"):
        await _get_oss_credential(db=MagicMock())


@patch("app.adapters.oss.pick_credential", new_callable=AsyncMock)
async def test_get_credential_missing_endpoint_raises(mock_pick):
    """config 缺 endpoint：KeyError 直接传播。"""
    from app.adapters.oss import _get_oss_credential

    cred = MagicMock()
    cred.id = 42
    cred.label = "AKIDxxx"
    cred.secret_enc = "SECRETxxx"
    cred.config = {"bucket": "my-bucket"}  # 没有 endpoint
    mock_pick.return_value = cred

    with pytest.raises(KeyError, match="endpoint"):
        await _get_oss_credential(db=MagicMock())
