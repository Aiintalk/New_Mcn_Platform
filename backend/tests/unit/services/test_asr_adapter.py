"""
Unit tests for ASR adapter (app/adapters/asr.py).

覆盖：
- submit_transcription：成功、失败、StatusText 非 SUCCESS、TaskId 缺失
- query_transcription：成功、失败
- transcribe：完整流程（RUNNING → SUCCESS）、超时、终态失败
- _get_asr_credential：secret_enc 格式错误
- AsrCallLog 写入验证

Mock 策略：纯 mock，不真实调外部阿里云。
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.asr import (
    query_transcription,
    submit_transcription,
    transcribe,
)


@pytest.fixture
def mock_db():
    """Mock AsyncSession：add 同步，commit 异步（适配 ASR adapter 写 AsrCallLog 后 commit）。"""
    db = MagicMock()
    db.commit = AsyncMock()
    return db


# ── submit_transcription ───────────────────────────────────────────────


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_submit_transcription_success(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """submit 成功：返回 TaskId，写 report_success。"""
    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.return_value = json.dumps({
        "StatusCode": 21050000,
        "StatusText": "SUCCESS",
        "TaskId": "task-abc-123",
        "RequestId": "req-xxx",
    }).encode("utf-8")

    task_id = await submit_transcription("https://example.com/a.mp3", db=mock_db, user_id=7)

    assert task_id == "task-abc-123"
    mock_report_success.assert_awaited_once()
    mock_report_failure.assert_not_awaited()


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_submit_transcription_network_failure(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """submit 网络失败：do_action_with_exception 抛异常 → report_failure + RuntimeError。"""
    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.side_effect = Exception("network timeout")

    with pytest.raises(RuntimeError, match="ASR submit_transcription failed"):
        await submit_transcription("https://example.com/a.mp3", db=mock_db)

    mock_report_failure.assert_awaited_once()
    mock_report_success.assert_not_awaited()


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_submit_transcription_status_not_success(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """submit 业务失败：StatusText != SUCCESS → report_failure + RuntimeError。"""
    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.return_value = json.dumps({
        "StatusCode": 41050002,
        "StatusText": "FILE_DOWNLOAD_FAILED",
    }).encode("utf-8")

    with pytest.raises(RuntimeError, match="ASR SubmitTask failed"):
        await submit_transcription("https://example.com/a.mp3", db=mock_db)

    mock_report_failure.assert_awaited_once()


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_submit_transcription_missing_task_id(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """submit 异常响应：SUCCESS 但无 TaskId → report_failure + RuntimeError。"""
    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.return_value = json.dumps({
        "StatusCode": 21050000,
        "StatusText": "SUCCESS",
        # 缺 TaskId
    }).encode("utf-8")

    with pytest.raises(RuntimeError, match="missing TaskId"):
        await submit_transcription("https://example.com/a.mp3", db=mock_db)

    mock_report_failure.assert_awaited_once()


# ── query_transcription ────────────────────────────────────────────────


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_query_transcription_success(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """query 成功：返回 dict，写 report_success。"""
    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.return_value = json.dumps({
        "StatusCode": 21050000,
        "StatusText": "SUCCESS",
        "Result": {"Sentences": [{"Text": "你好"}]},
    }).encode("utf-8")

    result = await query_transcription("task-abc", db=mock_db, user_id=9)

    assert result["StatusText"] == "SUCCESS"
    assert result["Result"]["Sentences"][0]["Text"] == "你好"
    mock_report_success.assert_awaited_once()


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_query_transcription_failure(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """query 网络失败：→ report_failure + RuntimeError。"""
    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.side_effect = Exception("connection reset")

    with pytest.raises(RuntimeError, match="ASR query_transcription failed"):
        await query_transcription("task-abc", db=mock_db)

    mock_report_failure.assert_awaited_once()


# ── transcribe ─────────────────────────────────────────────────────────


@patch("app.adapters.asr.asyncio.sleep", new_callable=AsyncMock)
@patch("app.adapters.asr.query_transcription", new_callable=AsyncMock)
@patch("app.adapters.asr.submit_transcription", new_callable=AsyncMock)
async def test_transcribe_success_first_running_then_success(
    mock_submit,
    mock_query,
    mock_sleep,
    mock_db,
):
    """transcribe：第 1 次 RUNNING → 第 2 次 SUCCESS → 返回拼接文本。"""
    mock_submit.return_value = "task-xyz"
    mock_query.side_effect = [
        {"StatusText": "RUNNING"},
        {
            "StatusText": "SUCCESS",
            "Result": {"Sentences": [{"Text": "你好"}, {"Text": "世界"}]},
        },
    ]

    text = await transcribe("https://example.com/a.mp3", db=mock_db, poll_interval=1, max_wait=60)

    assert text == "你好世界"
    mock_sleep.assert_awaited_once_with(1)


@patch("app.adapters.asr.asyncio.sleep", new_callable=AsyncMock)
@patch("app.adapters.asr.query_transcription", new_callable=AsyncMock)
@patch("app.adapters.asr.submit_transcription", new_callable=AsyncMock)
async def test_transcribe_success_queueing_then_success(
    mock_submit,
    mock_query,
    mock_sleep,
    mock_db,
):
    """transcribe：QUEUEING 也是中间态，继续轮询。"""
    mock_submit.return_value = "task-xyz"
    mock_query.side_effect = [
        {"StatusText": "QUEUEING"},
        {"StatusText": "RUNNING"},
        {"StatusText": "SUCCESS", "Result": {"Sentences": [{"Text": "OK"}]}},
    ]

    text = await transcribe("https://example.com/a.mp3", db=mock_db, poll_interval=1, max_wait=60)

    assert text == "OK"
    assert mock_sleep.await_count == 2


@patch("app.adapters.asr.query_transcription", new_callable=AsyncMock)
@patch("app.adapters.asr.submit_transcription", new_callable=AsyncMock)
async def test_transcribe_terminal_failure(
    mock_submit,
    mock_query,
    mock_db,
):
    """transcribe：终态失败 StatusText → 抛 RuntimeError。"""
    mock_submit.return_value = "task-xyz"
    mock_query.return_value = {
        "StatusCode": 41050002,
        "StatusText": "FILE_DOWNLOAD_FAILED",
    }

    with pytest.raises(RuntimeError, match="ASR transcribe failed"):
        await transcribe("https://example.com/a.mp3", db=mock_db, max_wait=60)


@patch("app.adapters.asr.asyncio.sleep", new_callable=AsyncMock)
@patch("app.adapters.asr.query_transcription", new_callable=AsyncMock)
@patch("app.adapters.asr.submit_transcription", new_callable=AsyncMock)
async def test_transcribe_timeout(
    mock_submit,
    mock_query,
    mock_sleep,
    mock_db,
):
    """transcribe：一直 RUNNING 超时 → RuntimeError。"""
    mock_submit.return_value = "task-xyz"
    mock_query.return_value = {"StatusText": "RUNNING"}

    with pytest.raises(RuntimeError, match="ASR transcribe timed out"):
        await transcribe(
            "https://example.com/a.mp3",
            db=mock_db,
            poll_interval=1,
            max_wait=2,  # 短超时便于测试
        )


# ── AsrCallLog 写入测试 ────────────────────────────────────────────────


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_submit_writes_call_log_success(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """submit 成功：finally 块写 AsrCallLog，operation=submit, status=success。"""
    from app.adapters.asr import submit_transcription as _submit
    from app.models.asr_call_log import AsrCallLog

    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.return_value = json.dumps({
        "StatusCode": 21050000,
        "StatusText": "SUCCESS",
        "TaskId": "task-log-1",
    }).encode("utf-8")

    await _submit("https://example.com/a.mp3", db=mock_db, user_id=7)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    asr_log_calls = [c for c in add_calls if isinstance(c, AsrCallLog)]
    assert len(asr_log_calls) == 1
    log = asr_log_calls[0]
    assert log.credential_id == 42
    assert log.user_id == 7
    assert log.operation == "submit"
    assert log.status == "success"
    assert log.task_id == "task-log-1"
    assert log.audio_url == "https://example.com/a.mp3"
    assert log.error_message is None
    assert isinstance(log.latency_ms, int)
    mock_db.commit.assert_awaited()


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_submit_writes_call_log_failure(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """submit 失败：finally 块写 AsrCallLog，status=fail + error_message，task_id=None。"""
    from app.adapters.asr import submit_transcription as _submit
    from app.models.asr_call_log import AsrCallLog

    mock_get_cred.return_value = (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.side_effect = Exception("network timeout")

    with pytest.raises(RuntimeError):
        await _submit("https://example.com/a.mp3", db=mock_db, user_id=7)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    asr_log_calls = [c for c in add_calls if isinstance(c, AsrCallLog)]
    assert len(asr_log_calls) == 1
    log = asr_log_calls[0]
    assert log.operation == "submit"
    assert log.status == "fail"
    assert log.task_id is None  # 失败时未拿到 TaskId
    assert "network timeout" in (log.error_message or "")


@patch("app.adapters.asr.report_success", new_callable=AsyncMock)
@patch("app.adapters.asr.report_failure", new_callable=AsyncMock)
@patch("app.adapters.asr.asyncio.to_thread", new_callable=AsyncMock)
@patch("app.adapters.asr._make_client")
@patch("app.adapters.asr._get_asr_credential", new_callable=AsyncMock)
async def test_query_writes_call_log_success(
    mock_get_cred,
    mock_make_client,
    mock_to_thread,
    mock_report_failure,
    mock_report_success,
    mock_db,
):
    """query 成功：finally 块写 AsrCallLog，operation=query。"""
    from app.adapters.asr import query_transcription as _query
    from app.models.asr_call_log import AsrCallLog

    mock_get_cred.return_value = (55, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
    mock_make_client.return_value = MagicMock()
    mock_to_thread.return_value = json.dumps({
        "StatusCode": 21050000,
        "StatusText": "SUCCESS",
        "Result": {"Sentences": []},
    }).encode("utf-8")

    await _query("task-abc", db=mock_db, user_id=12)

    add_calls = [c.args[0] for c in mock_db.add.call_args_list if c.args]
    asr_log_calls = [c for c in add_calls if isinstance(c, AsrCallLog)]
    assert len(asr_log_calls) == 1
    log = asr_log_calls[0]
    assert log.credential_id == 55
    assert log.user_id == 12
    assert log.operation == "query"
    assert log.status == "success"
    assert log.task_id == "task-abc"
    assert log.audio_url is None  # query 不记录 audio_url


# ── _get_asr_credential 边界 ──────────────────────────────────────────


@patch("app.adapters.asr.pick_credential", new_callable=AsyncMock)
async def test_get_credential_invalid_secret_format(mock_pick, mock_db):
    """secret_enc 不含换行：ValueError 直接传播。"""
    from app.adapters.asr import _get_asr_credential

    cred = MagicMock()
    cred.id = 42
    cred.config = {"app_key": "appkeyxxx", "region": "cn-shanghai"}
    cred.secret_enc = "only-one-line-no-newline"  # 格式错误
    mock_pick.return_value = cred

    with pytest.raises(ValueError, match="secret_enc"):
        await _get_asr_credential(db=mock_db)


@patch("app.adapters.asr.pick_credential", new_callable=AsyncMock)
async def test_get_credential_missing_app_key(mock_pick, mock_db):
    """config 缺 app_key：KeyError 直接传播。"""
    from app.adapters.asr import _get_asr_credential

    cred = MagicMock()
    cred.id = 42
    cred.config = {"region": "cn-shanghai"}  # 缺 app_key
    cred.secret_enc = "AKIDxxx\nSECRETxxx"
    mock_pick.return_value = cred

    with pytest.raises(KeyError, match="app_key"):
        await _get_asr_credential(db=mock_db)


@patch("app.adapters.asr.pick_credential", new_callable=AsyncMock)
async def test_get_credential_default_region(mock_pick, mock_db):
    """config 无 region：默认 cn-shanghai。"""
    from app.adapters.asr import _get_asr_credential

    cred = MagicMock()
    cred.id = 42
    cred.config = {"app_key": "appkeyxxx"}  # 无 region
    cred.secret_enc = "AKIDxxx\nSECRETxxx"
    mock_pick.return_value = cred

    result = await _get_asr_credential(db=mock_db)
    assert result == (42, "appkeyxxx", "AKIDxxx", "SECRETxxx", "cn-shanghai")
