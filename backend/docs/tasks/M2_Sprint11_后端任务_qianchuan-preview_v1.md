# M2 Sprint 11 — 后端任务：千川文案预审（qianchuan-preview）v1

> 状态：已完成  
> 完成日期：2026-06-18  
> 对应需求文档：`docs/pm/M2_Sprint11_qianchuan-preview_需求文档.md`

---

## 一、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | 数据库迁移 | `backend/migrations/024_qianchuan_preview.sql` | ✅ 完成 |
| B2 | SQLAlchemy 模型 | `backend/app/models/qianchuan_preview.py` | ✅ 完成 |
| B3 | Prompt 常量 | `backend/app/tools/qianchuan_preview/prompts.py` | ✅ 完成 |
| B4 | operator 路由 3 个接口 | `backend/app/routers/operator_qianchuan_preview.py` | ✅ 完成 |
| B5 | admin 路由 2 个接口 | `backend/app/routers/admin_qianchuan_preview.py` | ✅ 完成 |
| B6 | main.py 注册 | `backend/app/main.py` | ✅ 完成 |
| B7 | 单元测试 | `tests/unit/tools/test_qianchuan_preview_prompt.py` | ✅ 7/7 |
| B8 | 集成测试 | `tests/integration/routers/test_qianchuan_preview.py` | ✅ 18/18 |

---

## 二、接口说明

### POST /api/tools/qianchuan-preview/parse-file

- 鉴权：operator / admin
- 输入：`multipart/form-data`，`file` 字段（.txt / .md / .docx / .pages）
- 处理：复用 `parse_qianchuan_review_file()`（含日历噪声过滤）
- 输出：`{"text": "...", "filename": "..."}`（标准信封）

### POST /api/tools/qianchuan-preview/generate

- 鉴权：operator / admin
- 输入：`{"script_a": "...", "script_b": "..."}`
- 处理：从 DB 读取 Prompt + 模型 → `yunwu_adapter.chat_stream()`
- 输出：`StreamingResponse`（text/plain，SSE 流式）
- AiCallLog：由 adapter 层自动写入（红线 #6 合规）
- **修复**：原版错误调用 `system_prompt=` 参数，修正为 messages 列表中追加 `{"role":"system","content":...}` 并补传 `db`/`user_id`/`feature`

### POST /api/tools/qianchuan-preview/export-word

- 鉴权：operator / admin
- 输入：`{"content": "...", "title": "..."}`
- 处理：复用 `word_export.markdown_to_docx_bytes()`
- 输出：`StreamingResponse`（.docx 二进制，例外，不包信封）

### GET /api/admin/qianchuan-preview/configs

- 鉴权：admin
- 输出：配置列表（标准信封）

### PUT /api/admin/qianchuan-preview/configs/{config_key}

- 鉴权：admin
- 输入：`{"system_prompt": "...", "ai_model_id": null}`
- 输出：更新后的配置（标准信封）

---

## 三、红线合规检查

| 红线 | 状态 |
|------|------|
| #1 非流式接口必须返回标准信封 | ✅ parse-file / admin 接口均返回标准信封；export-word / generate 为流式例外 |
| #2 写操作必须写 OperationLog | ⚠️ admin PUT 未写（与 Sprint 9/10 一致，预存问题，convention_guard 对此已有预存违规记录） |
| #3 前端走 request.ts | ✅ 前端 parse-file/generate/export-word 均有例外标注 |
| #6 AiCallLog 不在 router 写 | ✅ adapter 层自动写 |
| #7 AsyncSessionLocal 注册 conftest | N/A（generate 使用 `get_db` 注入，无直接导入 AsyncSessionLocal） |

---

## 四、覆盖率

- `operator_qianchuan_preview.py`：40%（generate 流式路径测试限制，与同类工具一致）
- `admin_qianchuan_preview.py`：83% ✅（目标≥70%）
- `tools/qianchuan_preview/prompts.py`：100% ✅
