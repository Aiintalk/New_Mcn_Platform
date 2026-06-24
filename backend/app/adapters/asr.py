"""
app/adapters/asr.py

阿里云智能语音交互（ISI）适配器：录音文件识别（异步 API）。

API 模式：
- submit_transcription: POST SubmitTask → 返回 TaskId
- query_transcription:  GET GetTaskResult → 返回 StatusText + Result
- transcribe:           便捷封装（submit → 轮询 query → 返回文本）

凭证配置来自 service_credentials 表（provider="asr"）：
- label        = 备注名（如"上海生产环境"）
- config       = {"app_key": "...", "region": "cn-shanghai"}
- secret_enc   = "access_key_id\\naccess_key_secret"（与 OSS 同款 AK 体系，明文 Sprint 3 债务）

每次调用写 asr_call_logs 一条记录（仿 yunwu.py AiCallLog finally 模式）。
"""
import asyncio
import json
import time

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asr_call_log import AsrCallLog
from app.services.credential_selector import (
    pick_credential,
    report_failure,
    report_success,
)

# 阿里云 ISI 录音文件识别 POP RPC 常量
_API_VERSION = "2018-08-17"
_PRODUCT = "nls-filetrans"
_DEFAULT_REGION = "cn-shanghai"


def _make_domain(region: str) -> str:
    """根据 region 构造 filetrans 域名。"""
    return f"filetrans.{region}.aliyuncs.com"


def _make_client(access_key_id: str, access_key_secret: str, region: str) -> AcsClient:
    """构造 AcsClient（工厂函数，便于单测 mock）。"""
    return AcsClient(access_key_id, access_key_secret, region)


def _build_task_dict(app_key: str, audio_url: str, language: str) -> dict:
    """构造 SubmitTask 的 task 参数 dict（便于单测断言关键参数）。"""
    return {
        "appkey": app_key,
        "file_link": audio_url,
        "version": "4.0",
        "enable_words": False,
        # 阿里云 filetrans 默认只支持 8k/16k 采样率；抖音原声通常是 44.1k，
        # 必须开自适应，否则报 41050008 UNSUPPORTED_SAMPLE_RATE
        "enable_sample_rate_adaptive": True,
        "language_hints": [language],
    }


def _build_submit_request(app_key: str, audio_url: str, language: str) -> CommonRequest:
    """构造 SubmitTask 请求（便于单测 mock 和参数验证）。"""
    req = CommonRequest()
    req.set_domain(_make_domain(_DEFAULT_REGION))
    req.set_version(_API_VERSION)
    req.set_product(_PRODUCT)
    req.set_action_name("SubmitTask")
    req.set_method("POST")
    task = json.dumps(_build_task_dict(app_key, audio_url, language))
    req.add_body_params("Task", task)
    return req


def _build_query_request(task_id: str) -> CommonRequest:
    """构造 GetTaskResult 请求。"""
    req = CommonRequest()
    req.set_domain(_make_domain(_DEFAULT_REGION))
    req.set_version(_API_VERSION)
    req.set_product(_PRODUCT)
    req.set_action_name("GetTaskResult")
    req.set_method("GET")
    req.add_query_param("TaskId", task_id)
    return req


async def _get_asr_credential(
    db: AsyncSession,
) -> tuple[int, str, str, str, str]:
    """
    返回 (cred_id, app_key, access_key_id, access_key_secret, region)。

    注意：在 try 块外调用 —— 凭证缺失 / config 缺字段时直接抛异常，
    不应把"凭证配置错误"当作 ASR 调用失败累计。
    """
    credential = await pick_credential(provider="asr", db=db)
    config = credential.config or {}
    app_key = config["app_key"]
    region = config.get("region", _DEFAULT_REGION)

    secret_enc = credential.secret_enc or ""
    parts = secret_enc.split("\n", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            "ASR secret_enc 必须是 'access_key_id\\naccess_key_secret' 格式"
        )
    access_key_id, access_key_secret = parts
    return (credential.id, app_key, access_key_id, access_key_secret, region)


async def submit_transcription(
    audio_url: str,
    db: AsyncSession,
    user_id: int | None = None,
    language: str = "zh-CN",
) -> str:
    """
    提交录音文件识别任务。

    Args:
        audio_url: 音频文件的公网可访问 URL（本地文件需先上传 OSS）
        db: 数据库会话
        user_id: 调用方用户 ID（写入 asr_call_logs）
        language: BCP-47 语言代码（如 "zh-CN" / "en-US"）

    Returns:
        task_id（阿里云返回的 TaskId，用于后续查询）

    Raises:
        KeyError: 凭证 config 缺 app_key
        ValueError: secret_enc 格式错误
        RuntimeError: 提交失败
    """
    cred_id, app_key, ak_id, ak_secret, region = await _get_asr_credential(db)
    client = _make_client(ak_id, ak_secret, region)
    req = _build_submit_request(app_key, audio_url, language)

    start = time.monotonic()
    status = "success"
    error_message: str | None = None
    task_id: str | None = None
    try:
        resp_bytes = await asyncio.to_thread(client.do_action_with_exception, req)
        resp = json.loads(resp_bytes)
        status_text = resp.get("StatusText", "")
        if status_text != "SUCCESS":
            raise RuntimeError(
                f"ASR SubmitTask failed: {resp.get('StatusCode')} {status_text}"
            )
        task_id = resp.get("TaskId")
        if not task_id:
            raise RuntimeError(f"ASR SubmitTask response missing TaskId: {resp}")
        await report_success(cred_id, db)
        return task_id
    except Exception as e:
        status = "fail"
        error_message = str(e)[:500]
        await report_failure(cred_id, db)
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"ASR submit_transcription failed: {e}") from e
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        db.add(AsrCallLog(
            credential_id=cred_id,
            user_id=user_id,
            operation="submit",
            status=status,
            latency_ms=latency_ms,
            task_id=task_id,
            audio_url=audio_url,
            error_message=error_message,
        ))
        await db.commit()


async def query_transcription(
    task_id: str,
    db: AsyncSession,
    user_id: int | None = None,
) -> dict:
    """
    查询录音文件识别任务结果。

    Args:
        task_id: submit_transcription 返回的 TaskId
        db: 数据库会话
        user_id: 调用方用户 ID

    Returns:
        阿里云原始响应 dict（包含 StatusCode / StatusText / Result 等）

    Raises:
        RuntimeError: 查询失败
    """
    cred_id, _app_key, ak_id, ak_secret, region = await _get_asr_credential(db)
    client = _make_client(ak_id, ak_secret, region)
    req = _build_query_request(task_id)

    start = time.monotonic()
    status = "success"
    error_message: str | None = None
    try:
        resp_bytes = await asyncio.to_thread(client.do_action_with_exception, req)
        resp = json.loads(resp_bytes)
        await report_success(cred_id, db)
        return resp
    except Exception as e:
        status = "fail"
        error_message = str(e)[:500]
        await report_failure(cred_id, db)
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"ASR query_transcription failed: {e}") from e
    finally:
        latency_ms = int((time.monotonic() - start) * 1000)
        db.add(AsrCallLog(
            credential_id=cred_id,
            user_id=user_id,
            operation="query",
            status=status,
            latency_ms=latency_ms,
            task_id=task_id,
            error_message=error_message,
        ))
        await db.commit()


async def transcribe(
    audio_url: str,
    db: AsyncSession,
    user_id: int | None = None,
    poll_interval: int = 10,
    max_wait: int = 600,
    language: str = "zh-CN",
) -> str:
    """
    便捷封装：submit → 轮询 query → 返回完整转写文本。

    Args:
        audio_url: 音频 URL
        db: 数据库会话
        user_id: 调用方用户 ID
        poll_interval: 轮询间隔（秒），默认 10s（阿里云每 TaskId QPS 限制 1）
        max_wait: 最长等待时间（秒），默认 600s（10 分钟）
        language: BCP-47 语言代码

    Returns:
        转写文本（多条句子拼接）

    Raises:
        RuntimeError: 超时 / ASR 业务失败
    """
    deadline = time.monotonic() + max_wait
    task_id = await submit_transcription(
        audio_url, db, user_id=user_id, language=language
    )

    while time.monotonic() < deadline:
        r = await query_transcription(task_id, db, user_id=user_id)
        status_text = r.get("StatusText", "")
        if status_text in ("RUNNING", "QUEUEING"):
            await asyncio.sleep(poll_interval)
            continue
        if status_text == "SUCCESS":
            sentences = (r.get("Result") or {}).get("Sentences") or []
            return "".join(s.get("Text", "") for s in sentences)
        # 终态失败
        raise RuntimeError(
            f"ASR transcribe failed: {r.get('StatusCode')} {status_text}"
        )

    raise RuntimeError(f"ASR transcribe timed out after {max_wait}s (task_id={task_id})")
