# 千川剪辑预审（qianchuan-edit-review）迁移设计文档

> 状态：✅ 设计已确认，待实现
> 日期：2026-06-14
> 工具标识：`qianchuan-edit-review`
> 目标路由：`/workspace/qianchuan-edit-review`

---

## 一、背景

将旧架构（独立 Next.js 应用 `Ai_Toolbox/qianchuan-edit-review-web`）迁移到新平台（FastAPI + React/Vite）。功能 100% 还原，新增 JWT 鉴权和报告持久化（outputs 表）。

---

## 二、后端设计

### 2.1 新增路由文件（5 个）

所有接口挂载前缀 `/api/tools/`，统一 `Depends(require_password_changed)` 鉴权。

#### `routers/tool_extract_frames.py`

- **接口**：`POST /api/tools/extract-frames`
- **接收**：multipart `file`（视频）+ `count`（int，默认 8）
- **处理**：
  1. 保存到临时目录 `/tmp/frames-<uuid>/`
  2. `asyncio.create_subprocess_exec` 调 ffprobe 读时长
  3. 时间点策略：固定 0s/1s/2s，剩余帧在 3s~末均匀分布
  4. 逐帧异步 ffmpeg 截图（`scale='min(720,iw)':-2`，`-q:v 3`，timeout=10s/帧）
  5. 读为 base64，总超时 60s
  6. 清理临时目录（失败忽略）
- **返回**：`{"frames": [{"time": 0.0, "base64": "data:image/jpeg;base64,..."}], "duration": 32.5}`
- **错误**：文件缺失 400，ffprobe 失败 400，内部异常 500

#### `routers/tool_transcribe.py`

- **接口**：`POST /api/tools/transcribe`
- **接收**：multipart `file`（视频）+ `language`（str，默认 `zh`）
- **限制**：文件 > 25MB 返回 400
- **处理**：httpx 直接调云雾 `/audio/transcriptions`，模型 `gpt-4o-transcribe`；429 最多重试 3 次（间隔 3s/6s/9s）；timeout=120s
- **Key 来源**：环境变量 `YUNWU_API_KEY` / `YUNWU_BASE_URL`（音频接口，不走 credentials Key 池）
- **返回**：`{"text": "转录文字内容"}`
- **错误**：> 25MB 返回 400，上游失败 502

#### `routers/tool_chat_stream.py`

- **接口**：`POST /api/tools/chat-stream`
- **接收**：
  ```json
  {
    "messages": [{"role": "user", "content": [...多模态 parts...]}],
    "system_prompt": "你是千川广告剪辑预审专家...",
    "model": "gpt-4o",
    "max_tokens": 8000
  }
  ```
- **处理**：
  1. 拼 `{"role": "system", "content": system_prompt}` 到 messages 首位
  2. 调 `yunwu.chat_stream()`（走 credentials Key 池，写 AiCallLog）
  3. 返回 `StreamingResponse`，raw text 格式（与平台其他流式接口一致）
- **返回**：`text/plain; charset=utf-8` 流式文本
- **注意**：`AsyncSessionLocal` 需注册到 `tests/conftest.py` 的 `_SESSION_LOCAL_PATCH_TARGETS`（红线 #7）

#### `routers/tool_export_word.py`

- **接口**：`POST /api/tools/export-word`
- **接收**：`{"content": "Markdown文本", "title": "千川剪辑预审报告"}`
- **处理**：python-docx 渲染
  - 标题段落（居中）
  - 导出时间（居中，Asia/Shanghai 时区）
  - Markdown 正文转换：`# ` → H1（spacing 240/120），`## ` → H2（200/100），`### ` → H3（160/80），`- `/`* ` → 无序列表，`> ` → 引用（斜体，#666666，左缩进），`**文字**` → 行内加粗，空行 → 空段落
  - 字体：微软雅黑，11pt（22 half-points）
- **返回**：`.docx` 文件流，`Content-Disposition: attachment; filename*=UTF-8''千川预审报告_<日期>.docx`

#### `routers/tool_qianchuan_edit_review.py`

- **接口**：`POST /api/tools/qianchuan-edit-review/outputs`
- **接收**：
  ```json
  {
    "title": "千川剪辑预审_2026-06-14",
    "report": "AI生成的完整报告文本（Markdown）",
    "original_duration": 32.5,
    "ours_duration": 28.0,
    "original_frame_count": 8,
    "ours_frame_count": 8
  }
  ```
- **写入 outputs 表**：
  - `tool_code` = `qianchuan-edit-review`
  - `tool_name` = `千川剪辑预审`
  - `title` = 请求体 title
  - `content` = 请求体 report
  - `content_json` = `{original_duration, ours_duration, original_frame_count, ours_frame_count}`
  - `word_count` = `len(report)`
  - `created_by` = 当前用户 ID
- **写入 OperationLog**（红线 #2）：action=`save_output`，target_type=`output`
- **返回**：`success_response(data={"id": 123, "created_at": "..."})`（红线 #1）
- **注意**：`AsyncSessionLocal` 如使用需注册 conftest（红线 #7）

### 2.2 main.py 注册

新增 import 和 `app.include_router()` 5 条，挂 `/api` 前缀。

---

## 三、数据库迁移

**新文件**：`backend/migrations/019_qianchuan_edit_review.sql`

```sql
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
  'qianchuan-edit-review',
  '千川剪辑预审',
  '千川',
  '上传原版爆款与我方成片，AI看画面+文案，给出剪辑和画面插入建议',
  'online',
  '["AI生成","千川","剪辑","多模态","docx"]'::jsonb,
  (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM workspace_tools WHERE category = '千川')
)
ON CONFLICT (tool_code) DO NOTHING;
```

---

## 四、前端设计

### 4.1 新文件：`src/api/qianchuanEditReview.ts`

封装 5 个接口调用：
- `extractFrames(file, count)` — FormData，原生 fetch（FormData 例外，无需 request.ts）
- `transcribe(file, language)` — FormData，原生 fetch（FormData 例外）
- `chatStream(messages, systemPrompt, model, maxTokens)` — 原生 fetch + getReader()（SSE 例外）
- `exportWord(content, title)` — 原生 fetch + .blob()（Blob 下载例外）
- `saveOutput(body)` — `post()` from request.ts（标准 JSON，走 request.ts，红线 #3）

### 4.2 新文件：`src/pages/operator/QianChuanEditReviewPage.tsx`

**页面结构**：
```
顶部：标题「千川剪辑预审」+ 副标题
中部：
  左栏（绿色 emerald 主题）——原版爆款
    └ 视频上传区（拖拽/点击，25MB 限制）
    └ 「截帧 + 提取文案」按钮（处理中显示进度文案）
    └ 截帧预览（最多 5 帧缩略图，超出显示 +N）
    └ 文案文本框（可手动编辑）
  右栏（蓝色 blue 主题）——我方成片（同上）
底部：「开始预审」按钮（蓝色渐变，disabled 时灰色）
报告区（报告生成后出现）：
  └ 标题「剪辑预审报告」
  └ 流式 Markdown 渲染
  └ 「导出 Word」按钮（绿色）
  └ 「保存报告」按钮（新增，蓝色）
```

**状态管理**：React useState，无需全局 store（页面内自包含）。

**调用链**：
1. 上传视频 → 点击处理按钮 → 串行调 `extractFrames` → `transcribe`，更新本侧状态
2. 「开始预审」→ 构建多模态 parts（与旧版 buildMessage 逻辑完全一致）→ `chatStream`，流式更新 report
3. 「导出 Word」→ `exportWord`，触发 Blob 下载
4. 「保存报告」→ `saveOutput`，成功后提示「已保存」

**多模态消息构建规则**（完整保留旧版逻辑）：
```
parts = []
原版文本块（时长+文案）
if 原版有截帧: 逐帧插入 text("原版 第Xs：") + image_url(base64)
我方文本块（时长+文案）
if 我方有截帧: 逐帧插入 text("我方 第Xs：") + image_url(base64)
```

**System Prompt**：硬编码在前端，随 `chatStream` 请求体传给后端，后端透传。

### 4.3 修改：`src/App.tsx`

新增 import + Route：
```tsx
import QianChuanEditReviewPage from './pages/operator/QianChuanEditReviewPage';
// 在 OperatorLayout 下新增：
<Route path="/workspace/qianchuan-edit-review" element={<QianChuanEditReviewPage />} />
```

---

## 五、开发红线合规清单

| 红线 | 涉及接口/文件 | 处理方式 |
|------|-------------|---------|
| #1 标准信封 | `tool_qianchuan_edit_review.py` | 用 `success_response()` 包装返回 |
| #2 OperationLog | `tool_qianchuan_edit_review.py` POST | 写 OperationLog（action=save_output） |
| #3 前端走 request.ts | `saveOutput` | 用 `post()` from request.ts |
| #3 例外声明 | `extractFrames`/`transcribe`/`exportWord`/`chatStream` | FormData/Blob/SSE 例外，原生 fetch |
| #7 conftest 注册 | `tool_chat_stream.py` | 注册 `_SESSION_LOCAL_PATCH_TARGETS` |

---

## 六、测试要点

- 截帧接口：mock subprocess，验证 base64 返回格式
- 转录接口：mock httpx，验证 429 重试逻辑（3次，间隔递增）
- chat-stream 接口：验证 system_prompt 拼入 messages 首位，验证鉴权
- export-word 接口：验证 .docx 文件流返回，验证 Content-Disposition header
- outputs 接口：验证写库字段，验证 OperationLog 写入
- 前端守卫测试（`conventionGuard.test.ts`）：新增的 API 文件中无裸 fetch（例外已标注）

---

## 七、交付物清单

| # | 交付物 | 位置 |
|---|--------|------|
| 1 | 需求文档 | `Ai_Toolbox/系统架构方案及M1进度同步/qianchuan-edit-review-迁移需求文档.md` |
| 2 | 设计文档（本文件） | `docs/superpowers/specs/2026-06-14-qianchuan-edit-review-design.md` |
| 3 | 后端任务文档 | `backend/docs/tasks/M2_SprintXX_后端任务_千川剪辑预审迁移_v1.md` |
| 4 | 前端任务文档 | `frontend/docs/tasks/M2_SprintXX_前端任务_千川剪辑预审迁移_v1.md` |
| 5 | 数据库迁移文件 | `backend/migrations/019_qianchuan_edit_review.sql` |
| 6 | 测试报告 | `backend/docs/tests/` |
| 7 | PM 记忆与状态更新 | `docs/pm/PM_记忆与状态_M2.md` |
