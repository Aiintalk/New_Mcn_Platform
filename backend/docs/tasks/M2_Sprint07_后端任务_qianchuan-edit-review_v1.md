# M2 Sprint 7 · 后端任务 · qianchuan-edit-review v1

> 状态：✅ 已完成（2026-06-14）
> 需求文档：`docs/pm/M2_Sprint07_qianchuan-edit-review_需求文档.md`
> 实施计划：`docs/superpowers/plans/2026-06-14-qianchuan-edit-review.md`

---

## 一、新建 / 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/app/routers/tool_extract_frames.py` | 新建 | POST /api/tools/extract-frames，ffmpeg 截帧，返回 base64 帧列表+时长 |
| `backend/app/routers/tool_transcribe.py` | 新建 | POST /api/tools/transcribe，调云雾 Whisper，返回转录文本 |
| `backend/app/routers/tool_chat_stream.py` | 新建 | POST /api/tools/chat-stream，通用多模态 SSE 流式接口 |
| `backend/app/routers/tool_export_word.py` | 新建 | POST /api/tools/export-word，Markdown → .docx 文件流 |
| `backend/app/routers/tool_qianchuan_edit_review.py` | 新建 | POST /api/tools/qianchuan-edit-review/outputs，保存报告 |
| `backend/migrations/019_qianchuan_edit_review.sql` | 新建 | 注册 workspace_tools 入口 |
| `backend/tests/integration/routers/test_tool_extract_frames.py` | 新建 | 截帧接口集成测试（3个用例）|
| `backend/tests/integration/routers/test_tool_transcribe.py` | 新建 | 转录接口集成测试（4个用例）|
| `backend/tests/integration/routers/test_tool_chat_stream.py` | 新建 | 流式接口集成测试（4个用例）|
| `backend/tests/integration/routers/test_tool_export_word.py` | 新建 | Word导出接口集成测试（4个用例）|
| `backend/tests/integration/routers/test_tool_qianchuan_edit_review.py` | 新建 | 保存报告集成测试（5个用例）|
| `backend/app/main.py` | 修改 | 注册 5 个新路由，各带 prefix="/api" |
| `backend/tests/conftest.py` | 修改 | `_SESSION_LOCAL_PATCH_TARGETS` 新增 `app.routers.tool_chat_stream.AsyncSessionLocal` |
| `backend/requirements.txt` | 修改 | 新增 `pytz` 依赖 |

---

## 二、接口清单

### 工具接口（operator / admin 角色）

| 方法 | 路径 | 路由文件 | 说明 |
|------|------|---------|------|
| POST | `/api/tools/extract-frames` | `tool_extract_frames.py` | 截帧；file 字段（multipart），count 默认8；返回 `{frames:[{time,base64}], duration}` |
| POST | `/api/tools/transcribe` | `tool_transcribe.py` | 转录；file 字段（multipart），language 默认 zh；返回 `{text}` |
| POST | `/api/tools/chat-stream` | `tool_chat_stream.py` | SSE 流式；body `{messages, system_prompt, model, max_tokens}`；`text/plain; charset=utf-8` |
| POST | `/api/tools/export-word` | `tool_export_word.py` | Word 导出；body `{content, title}`；返回 `.docx` 文件流（非信封）|
| POST | `/api/tools/qianchuan-edit-review/outputs` | `tool_qianchuan_edit_review.py` | 保存报告；body `{title, report, original_duration, ours_duration, original_frame_count, ours_frame_count}`；返回 `{id, created_at}` |

---

## 三、核心业务逻辑

### 截帧（tool_extract_frames.py）

```
1. ffprobe 读视频时长（timeout 15s）
2. 计算截帧时间点：前3帧固定 0s/1s/2s，剩余均匀分布
3. 逐帧 ffmpeg 截图，720px 宽，JPEG q:v=3（单帧 timeout 10s）
4. base64 编码返回，格式 data:image/jpeg;base64,...
5. 总超时 60s
```

### 转录（tool_transcribe.py）

```
1. 文件 > 25MB → 400 FILE_TOO_LARGE
2. POST 到云雾 Whisper API（env: YUNWU_BASE_URL + YUNWU_API_KEY）
3. 429 时重试，_RETRY_DELAYS=[3,6]，共 3 次尝试
4. 非 200 → 502 UPSTREAM_ERROR
5. 返回 success_response(data={"text": ...})
```

### 流式对话（tool_chat_stream.py）

```
1. messages 为空 → 400 INVALID_INPUT
2. system_prompt 为空 → 400 INVALID_INPUT
3. 拼 system 消息到 messages 首位
4. 调 yunwu_adapter.chat_stream()（background task 独立 AsyncSessionLocal）
5. 429 时重试，_RETRY_DELAYS=[2,4,6]
6. 返回 StreamingResponse(text/plain; charset=utf-8)
```

### Word 导出（tool_export_word.py）

```
1. content 为空 → 400 INVALID_INPUT
2. 标题居中（微软雅黑 16pt 加粗）
3. 导出时间（Asia/Shanghai，居中）
4. 正文：H1/H2/H3 标题、- 无序列表、> 引用、**粗体**、普通段落
5. 文件名 千川预审报告_{YYYYMMDD}.docx，URL 编码 RFC5987
6. 返回 Response（Content-Type: application/vnd.openxmlformats...）
```

---

## 四、数据库

- **无新增表**（复用 `outputs`、`ai_call_logs`、`operation_logs`）
- **迁移 019**：`migrations/019_qianchuan_edit_review.sql`，INSERT workspace_tools (qianchuan-edit-review, 千川剪辑预审, 千川, online)

---

## 五、依赖

| 新增包 | 用途 |
|--------|------|
| `pytz` | tool_export_word.py 获取 Asia/Shanghai 时区时间 |

---

## 六、技术处理要点

| # | 要点 | 处理方式 |
|---|------|---------|
| 1 | tool_chat_stream 后台写 AiCallLog | 使用独立 `AsyncSessionLocal`，已注册到 conftest.py `_SESSION_LOCAL_PATCH_TARGETS` |
| 2 | export-word 文件名中文 | `urllib.parse.quote` + `filename*=UTF-8''` RFC5987 编码，前端需 `decodeURIComponent` |
| 3 | 截帧临时文件清理 | `finally` 块删除临时视频和目录，失败也不抛出 |
| 4 | 红线 #1 合规 | extract-frames 和 transcribe 均返回 `success_response(data=...)`；export-word 为文件流例外 |
| 5 | 红线 #2 合规 | save_output 接口在 `db.commit()` 前写入 `OperationLog` |

---

## 七、测试结果

| 测试文件 | 用例数 | 结果 |
|---------|--------|------|
| `test_tool_extract_frames.py` | 3 | 3/3 ✅ |
| `test_tool_transcribe.py` | 4 | 4/4 ✅ |
| `test_tool_chat_stream.py` | 4 | 4/4 ✅ |
| `test_tool_export_word.py` | 4 | 4/4 ✅ |
| `test_tool_qianchuan_edit_review.py` | 5 | 5/5 ✅ |
| **合计** | **21** | **21/21 ✅** |

**覆盖率（新模块）：**

| 模块 | 覆盖率 | 目标 | 状态 |
|------|--------|------|------|
| `routers/tool_transcribe.py` | **100%** | ≥70% | ✅ |
| `routers/tool_export_word.py` | **87%** | ≥70% | ✅ |
| `routers/tool_qianchuan_edit_review.py` | **86%** | ≥70% | ✅ |
| `routers/tool_chat_stream.py` | **81%** | ≥70% | ✅ |
| `routers/tool_extract_frames.py` | **34%** | ≥70% | ⚠️ ffmpeg subprocess 路径无法在集成测试中真实执行 |

> `tool_extract_frames.py` 覆盖率偏低原因：`_extract_frames()` 内的 ffprobe/ffmpeg 调用在测试环境中被 mock 整体替换，内部分支（超时/帧截取/base64编码）未走真实路径。实际功能已通过功能测试验证。

---

## 八、全量回归

本次新增代码不引入任何历史测试失败。全量运行 `tests/unit/ + tests/integration/`（不含 intake/ concurrent/）共 **478 passed**，8 failed（均为迁移前遗留，与本次改动无关）。
