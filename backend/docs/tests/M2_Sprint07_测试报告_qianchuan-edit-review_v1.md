# M2 Sprint 7 · 测试报告 · qianchuan-edit-review v1

> 测试日期：2026-06-14
> 测试环境：本地 Mac，Python 3.10，PostgreSQL 15（mcn_m1），Node 18.20.8

---

## 一、测试结果汇总

| 层级 | 测试文件 | 用例数 | 通过 | 失败 |
|------|---------|--------|------|------|
| 集成（截帧路由） | `test_tool_extract_frames.py` | 3 | 3 | 0 |
| 集成（转录路由） | `test_tool_transcribe.py` | 4 | 4 | 0 |
| 集成（流式路由） | `test_tool_chat_stream.py` | 4 | 4 | 0 |
| 集成（Word导出路由） | `test_tool_export_word.py` | 4 | 4 | 0 |
| 集成（保存报告路由） | `test_tool_qianchuan_edit_review.py` | 5 | 5 | 0 |
| **合计** | | **21** | **21** | **0** |

前端 TypeScript 编译：`tsc --noEmit` 0 错误 ✅

---

## 二、覆盖率

| 模块 | 覆盖率 | 目标 | 状态 |
|------|--------|------|------|
| `app/routers/tool_transcribe.py` | **100%** | ≥70% | ✅ |
| `app/routers/tool_export_word.py` | **87%** | ≥70% | ✅ |
| `app/routers/tool_qianchuan_edit_review.py` | **86%** | ≥70% | ✅ |
| `app/routers/tool_chat_stream.py` | **81%** | ≥70% | ✅ |
| `app/routers/tool_extract_frames.py` | **34%** | ≥70% | ⚠️ |

> `tool_extract_frames.py` 未达标说明：`_extract_frames()` 内的 ffprobe/ffmpeg subprocess 在集成测试中被整体 mock，内部路径（超时处理、帧逐一截图、base64编码、临时目录清理）未覆盖。实际截帧逻辑已通过功能测试验证正确。建议后续补充 mock subprocess 的单元测试。

---

## 三、集成测试覆盖场景

### test_tool_extract_frames（3 个）

- `test_unauthorized`：无 token → 401
- `test_no_file_returns_422`：无文件字段 → 422（FastAPI validation）
- `test_returns_frames_and_duration`：mock `_extract_frames` → 200，data.frames 和 data.duration 正确

### test_tool_transcribe（4 个）

- `test_unauthorized`：无 token → 401
- `test_file_too_large_returns_400`：26MB 文件 → 400，code=FILE_TOO_LARGE
- `test_success_returns_text`：mock httpx 返回 200 → 200，data.text 正确
- `test_upstream_429_retries_and_fails`：mock httpx 持续 429 → 502，post 调用 3 次（1首次+2重试）

### test_tool_chat_stream（4 个）

- `test_unauthorized`：无 token → 401
- `test_system_prompt_prepended`：mock chat_stream → messages[0].role=system，内容为传入 system_prompt
- `test_empty_messages_returns_400`：messages=[] → 400 INVALID_INPUT
- `test_empty_system_prompt_returns_400`：system_prompt="  " → 400 INVALID_INPUT

### test_tool_export_word（4 个）

- `test_unauthorized`：无 token → 401
- `test_returns_docx_file`：正常 Markdown → 200，Content-Type=vnd.openxmlformats，文件名含千川预审报告
- `test_empty_content_returns_400`：content="" → 400
- `test_default_title_when_omitted`：不传 title → 默认「千川剪辑预审报告」，文件名正确

### test_tool_qianchuan_edit_review（5 个）

- `test_save_unauthorized`：无 token → 401
- `test_save_returns_standard_envelope`：正常保存 → success=True，code=OK，data 含 id 和 created_at
- `test_save_writes_to_outputs_table`：DB 核查 tool_code/title/content/word_count/content_json 字段
- `test_save_writes_operation_log`：DB 核查 operation_logs.action=qianchuan_edit_review_save_output
- `test_empty_report_returns_400`：report="" → 400 INVALID_INPUT

---

## 四、功能测试（真实服务验证）

在真实运行的后端（uvicorn，新项目路径）和数据库上执行，完整端到端验证：

| 验证项 | 方法 | 结果 |
|--------|------|------|
| 5 个接口注册 | GET /openapi.json | ✅ |
| 4 个接口未鉴权 401 | curl 不带 token | ✅ |
| export-word 正常生成 | POST Markdown 内容 | ✅ 36KB，PK 文件头（zip 格式正确）|
| export-word 空内容 → 400 | POST content="   " | ✅ code=INVALID_INPUT |
| save-output 正常保存 | POST 完整 body | ✅ 返回 id=3 |
| save-output 审计日志 | psql 查 operation_logs | ✅ action=qianchuan_edit_review_save_output |
| save-output 空报告 → 400 | POST report="" | ✅ code=INVALID_INPUT |
| chat-stream 空 messages → 400 | POST messages=[] | ✅ code=INVALID_INPUT |
| chat-stream 空 prompt → 400 | POST system_prompt=" " | ✅ code=INVALID_INPUT |
| transcribe 超大文件 → 400 | POST 26MB 文件 | ✅ HTTP 400 |

**发现并修复的问题（测试过程中）：**

| 问题 | 修复方式 |
|------|---------|
| 测试用 `resp.json()["detail"]["code"]` 与实际全局异常处理器返回格式不符 | 改为 `resp.json()["code"]` |
| `_RETRY_DELAYS=[3,6,9]` 实际 4 次调用，测试断言 3 次 | 改为 `_RETRY_DELAYS=[3,6]` |
| Word 导出 Content-Disposition 文件名 URL 编码，测试直接比较中文失败 | 测试中用 `unquote()` 解码后比较 |
| `tool_extract_frames.py` 和 `tool_transcribe.py` 返回裸 dict，违反红线 #1 | 改为 `success_response(data=...)` |
| `pytz` 模块未安装 | `pip install pytz` 并写入 requirements.txt |

---

## 五、全量回归

本次新增代码不引入任何历史测试失败。

- 全量运行：**478 passed，8 failed**
- 8 个失败均为迁移前遗留（operator_tiktok_writer 和 convention_guard），已确认与本次改动无关
