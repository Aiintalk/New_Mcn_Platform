# M2 — 后端任务：ASR 完整方案

> 状态：**已完成**（PR #4 已提交待合并）
> 完成日期：2026-06-22
> 对应需求文档：`docs/pm/M2_ASR_完整方案_需求文档.md`
> 对应分支：`feature/asr-tab`

---

## 一、范围（本次后端任务）

涵盖 ASR 完整方案的所有后端工作：
- Migration 029（asr_call_logs 表）
- ORM 模型 AsrCallLog + 注册 __init__.py（同时补注册 OssCallLog）
- ASR adapter 3 公开函数 + 5 内部 helper（POP RPC + CommonRequest）
- admin_asr.py 3 个统计接口（参照 admin_oss.py）
- admin_credentials.py 测试端点扩 ASR 分支（GetTaskResult + probe TaskId）
- main.py 注册 admin_asr router
- requirements.txt 加 aliyun-python-sdk-core>=2.13.12
- 单测 + 集测 + 凭证测试全绿

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | Migration 029 asr_call_logs | `backend/migrations/029_asr_call_logs.sql` | ✅ |
| B2 | ORM 模型 AsrCallLog | `backend/app/models/asr_call_log.py` | ✅ |
| B3 | 注册 AsrCallLog + 补注册 OssCallLog 到 `__init__.py` | `backend/app/models/__init__.py` | ✅ |
| B4 | ASR adapter 3 公开 + 5 helper | `backend/app/adapters/asr.py` | ✅ |
| B5 | admin_asr.py 3 统计接口 | `backend/app/routers/admin_asr.py` | ✅ |
| B6 | admin_credentials.py 测试端点 ASR 分支 + `_record_test_outcome` 重构 | `backend/app/routers/admin_credentials.py` | ✅ |
| B7 | main.py 注册 admin_asr_router | `backend/app/main.py` | ✅ |
| B8 | requirements.txt 加 `aliyun-python-sdk-core>=2.13.12` | `backend/requirements.txt` | ✅ |
| B9 | 单元测试 16 用例 | `backend/tests/unit/services/test_asr_adapter.py` | ✅ |
| B10 | 集成测试 10 用例 | `backend/tests/integration/routers/test_admin_asr.py` | ✅ |
| B11 | 凭证测试扩 4 ASR 用例 | `backend/tests/integration/routers/test_credentials.py` | ✅ |
| B12 | 文档同步（Base_API §10B + Base_Database §24 + README） | 多处 | ✅ |

## 三、API 设计

### 3.1 ASR Adapter（app/adapters/asr.py）

```python
# 常量
_API_VERSION = "2018-08-17"
_PRODUCT = "nls-filetrans"
_DEFAULT_REGION = "cn-shanghai"

# 公开函数
async def submit_transcription(audio_url: str, db: AsyncSession, user_id=None, language="zh-CN") -> str: ...
async def query_transcription(task_id: str, db: AsyncSession, user_id=None) -> dict: ...
async def transcribe(audio_url: str, db: AsyncSession, user_id=None, poll_interval=10, max_wait=600) -> str: ...

# 内部 helper
def _make_domain(region: str) -> str: ...        # → f"{_PRODUCT}.{region}.aliyuncs.com"
def _make_client(ak_id, ak_secret, region) -> AcsClient: ...
def _build_submit_request(...) -> CommonRequest: ...  # Action=SubmitTask
def _build_query_request(task_id) -> CommonRequest: ...  # Action=GetTaskResult
async def _get_asr_credential(db) -> tuple: ...  # cred_id, app_key, ak_id, ak_secret, region
```

凭证解析关键：`parts = secret_enc.split("\n", 1)`，校验 `len(parts) == 2` 且两部分非空。

`transcribe()` 轮询逻辑：
```python
deadline = time.monotonic() + max_wait
task_id = await submit_transcription(...)
while time.monotonic() < deadline:
    r = await query_transcription(task_id, ...)
    status_text = r.get("StatusText", "")
    if status_text in ("RUNNING", "QUEUEING"):
        await asyncio.sleep(poll_interval); continue
    if status_text == "SUCCESS":
        return "".join(s["Text"] for s in r["Result"]["Sentences"])
    raise RuntimeError(f"ASR failed: {r.get('StatusCode')} {status_text}")
raise RuntimeError(f"ASR timed out after {max_wait}s")
```

### 3.2 统计接口（admin_asr.py）

直接 clone admin_oss.py，SQL 表名 `oss_call_logs` → `asr_call_logs`，provider `'oss'` → `'asr'`。

### 3.3 测试端点扩展（admin_credentials.py）

provider='asr' 分支流程：
```
读 cred → 解析 config.app_key + config.region (默认 cn-shanghai) + secret_enc.split("\n")
→ _make_asr_client(ak_id, ak_secret, region)
→ req = _build_asr_query_request("test-connectivity-probe-task-id")
→ asyncio.to_thread(client.do_action_with_exception, req)
→ 预期业务错误（41050010 TASK_EXPIRED），但状态码不是签名/认证错误
→ 成功：返回 {status:ok, latency_ms, status_text, status_code}
→ 失败：返回 {status:error, latency_ms, error}
```

提取 `_record_test_outcome(cred_id, user, request, status, latency_ms, provider, error_msg)` 共用辅助函数，消除 OSS/ASR 两分支重复。

## 四、测试覆盖

### 4.1 单元测试（test_asr_adapter.py，16 用例）

| 分类 | 用例数 | 关键用例 |
|------|--------|----------|
| submit | 4 | 成功返 TaskId / 网络失败 / 状态非 SUCCESS / 响应缺 TaskId |
| query | 2 | 成功返 dict / 失败 |
| transcribe | 4 | RUNNING→SUCCESS / QUEUEING+RUNNING→SUCCESS / 终态失败 / 超时 |
| AsrCallLog 写入 | 3 | submit 成功 / submit 失败 / query 成功 |
| _get_asr_credential 边界 | 3 | secret 格式错（单行）/ 缺 app_key / 默认 region |

### 4.2 集成测试（test_admin_asr.py，10 用例）

- TestAdminAsrAuth：4 鉴权
- TestAsrStats：shape + with_data
- TestAsrOperations：shape + with_data（验证 success_rate 0-1 范围）
- TestAsrUsers：shape + with_data

### 4.3 凭证测试（test_credentials.py 扩 4 ASR 用例）

- test_test_credential_asr_ok：mock _make_asr_client.do_action_with_exception 返 41050010，验证 status_text=FILE_TRANS_TASK_EXPIRED
- test_test_credential_asr_failure：mock 抛异常，验证 status=error
- test_test_credential_asr_missing_app_key：config={}，预期 VALIDATION_ERROR
- test_test_credential_asr_invalid_secret_format：secret_enc="only-one-line"，预期 VALIDATION_ERROR

## 五、关键约定

- ASR `secret_enc` 格式：`"access_key_id\naccess_key_secret"`（两行）
- ASR `config`：`{app_key, region}`，region 默认 cn-shanghai
- operation 分类：`submit`（带 audio_url）/ `query`（带 task_id，无 audio_url）
- `transcribe()` 不写日志（由 submit + query 两个子调用各自写）
- 测试端点不调 SubmitTask（避免测试音频依赖），改用 GetTaskResult + probe TaskId
- `aliyun-python-sdk-core>=2.13.12`（与 oss2 兼容下限，避免版本冲突）
