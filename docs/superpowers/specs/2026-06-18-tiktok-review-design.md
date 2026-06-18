# tiktok-review 迁移设计文档

> 创建日期：2026-06-18
> 工具代码：`tiktok-review`
> 迁移来源：`Ai_Toolbox_new/tiktok-review-web`
> 阶段：M2 Sprint 13

---

## 一、功能定位

**TT内容复盘**：上传/粘贴两条 TikTok 视频文案（原版爆款 + 仿写版），各填点赞数，AI 从 7 个维度对比分析差距，输出流式复盘报告，支持保存到产出中心 + 导出 Word。

### 旧工具核心能力

| 能力 | 旧实现 |
|------|--------|
| 视频转文案 | 调云雾 Whisper，语言写死 `ko`（韩语） |
| AI 分析 | 调云雾 LLM，模型写死 `claude-opus-4-6-thinking`，Prompt 硬编码 |
| 导出 Word | `docx` 库，Markdown → Word |
| 产出保存 | ❌ 无，仅页面临时展示 |

---

## 二、迁移决策

| 项目 | 决策 | 理由 |
|------|------|------|
| 转录语言 | 固定 `ko`（韩语） | 该工具分析的 TikTok 视频以韩语为主 |
| 输入字段 | 保持原样（文案 + 点赞数） | 无需扩展 |
| 产出中心 | 接入，支持历史列表 | 迁移红线 #2 硬约束 |
| Prompt/模型配置 | 一个配置项（`config_key='default'`） | 沿用已迁工具模式，管理端可配 |
| 转录接口 | 复用公共 `POST /api/tools/transcribe` | 零新增代码，与其他工具一致 |
| Word 导出 | 复用 `app/services/word_export.py` | 零新增代码 |

---

## 三、架构设计

### 数据流

```
前端运营端                         后端                          外部
──────────────────                 ──────────────────────        ──────────
TiktokReviewPage.tsx

  [两栏输入区]
  原版爆款：
    上传视频 ──────────────────→  POST /api/tools/transcribe  →  Whisper API
    文案文本框（手动/转录结果）
    点赞数

  仿写版：（同上）

  [开始复盘] ────────────────→   POST /api/tools/tiktok-review/generate (SSE)
                                   ├ 读 tiktok_review_configs（config_key='default'）
                                   ├ 走 yunwu adapter（流式）
                                   ├ 写 ai_call_logs（finally）
                                   └ 写 OperationLog

  [保存报告] ────────────────→   POST /api/tools/tiktok-review/save
                                   └ 写 outputs 表（tool_code='tiktok-review'）

  [历史报告] ────────────────→   GET  /api/tools/tiktok-review/outputs

  [导出 Word] ───────────────→   POST /api/tools/tiktok-review/export-word
                                   └ 复用 word_export 服务

前端管理端
──────────────────
TiktokReviewConfigTab.tsx  ─────→  GET  /api/admin/tiktok-review/config
                            ─────→  POST /api/admin/tiktok-review/config
```

---

## 四、后端详细设计

### 4.1 数据库迁移 `026_tiktok_review.sql`

```sql
-- 表：tiktok_review_configs
CREATE TABLE IF NOT EXISTS tiktok_review_configs (
    id            SERIAL PRIMARY KEY,
    config_key    VARCHAR(50)  NOT NULL UNIQUE,
    ai_model_id   INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
    system_prompt TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 触发器（自动更新 updated_at）
CREATE TRIGGER trg_tiktok_review_configs_updated ...

-- workspace_tools 注册
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES ('tiktok-review', 'TT内容复盘', '内容创作', '...', 'dev', '...', 16)
ON CONFLICT (tool_code) DO NOTHING;

-- 默认配置（含旧工具 SYSTEM_PROMPT）
INSERT INTO tiktok_review_configs (config_key, system_prompt, is_active)
VALUES ('default', '<旧工具 SYSTEM_PROMPT 全文>', true)
ON CONFLICT (config_key) DO NOTHING;
```

### 4.2 SQLAlchemy 模型 `app/models/tiktok_review.py`

字段：`id / config_key / ai_model_id / system_prompt / is_active / created_at / updated_at`
（结构与 `QianchuanReviewConfig` 完全一致）

### 4.3 运营端路由 `app/routers/operator_tiktok_review.py`

| 接口 | 说明 |
|------|------|
| `POST /api/tools/tiktok-review/generate` | SSE 流式，入参：`original_transcript / original_likes / copycat_transcript / copycat_likes`，读 DB 配置，走 yunwu adapter，写 `ai_call_logs`（finally）+ `OperationLog` |
| `POST /api/tools/tiktok-review/save` | 保存报告到 `outputs`，入参：`content / title`，写 `OperationLog` |
| `GET  /api/tools/tiktok-review/outputs` | 历史报告列表，分页（`page / page_size`），按 `created_at DESC` |
| `POST /api/tools/tiktok-review/export-word` | 导出 Word，复用 `word_export.markdown_to_docx_bytes`，返回文件流 |

**鉴权**：全部接口要求 `operator` 或 `admin` 角色 + 已改密。

**SSE 格式**：裸文本流（与 tiktok-writer 一致），`Content-Type: text/plain; charset=utf-8`。

### 4.4 管理端路由 `app/routers/admin_tiktok_review.py`

| 接口 | 说明 |
|------|------|
| `GET  /api/admin/tiktok-review/config` | 读取 `config_key='default'` 的配置，返回标准信封 |
| `POST /api/admin/tiktok-review/config` | 更新 Prompt + `ai_model_id`，写 `OperationLog` |

**鉴权**：`admin` 角色。

### 4.5 main.py 注册

```python
from app.routers import operator_tiktok_review, admin_tiktok_review
app.include_router(operator_tiktok_review.router, prefix="/api")
app.include_router(admin_tiktok_review.router,    prefix="/api")
```

---

## 五、前端详细设计

### 5.1 文件清单

| 文件 | 说明 |
|------|------|
| `src/api/tiktokReview.ts` | API 层：generate（SSE）/ save / outputs / exportWord / getConfig / updateConfig |
| `src/types/tiktokReview.ts` | 类型：`VideoSide / TiktokReviewOutput / TiktokReviewConfig` |
| `src/pages/operator/TiktokReviewPage.tsx` | 运营端主页面 |
| `src/pages/admin/TiktokReviewConfigTab.tsx` | 管理端配置 Tab |

### 5.2 运营端页面布局

```
┌─────────────────────────────────────────┐
│          TT内容复盘                      │
├───────────────────┬─────────────────────┤
│  原版爆款          │  仿写版              │
│  ┌─────────────┐  │  ┌─────────────┐   │
│  │ 上传视频     │  │  │ 上传视频     │   │
│  └─────────────┘  │  └─────────────┘   │
│  [转文案] 按钮     │  [转文案] 按钮      │
│  文案文本框        │  文案文本框         │
│  点赞数输入框      │  点赞数输入框       │
├───────────────────┴─────────────────────┤
│              [开始复盘]                  │
├─────────────────────────────────────────┤
│  复盘报告（SSE 流式渲染 Markdown）        │
│                        [保存] [导出Word] │
└─────────────────────────────────────────┘
```

- 转录：调公共 `/api/tools/transcribe`，语言固定 `ko`
- SSE：逐字追加到报告区，滚动跟随
- 保存：调 `/save`，成功后 Toast 提示
- 导出：调 `/export-word`，触发浏览器下载

### 5.3 路由注册

`/workspace/tiktok-review` → `TiktokReviewPage`（懒加载）

### 5.4 管理端 Tab

在现有管理端「服务配置」页面，新增 `TiktokReviewConfigTab`：
- Prompt 文本域（可编辑）
- 模型下拉（从 `ai_models` 列表选）
- 保存按钮

---

## 六、契约文档更新

- **Base_API**：新增 §N `tiktok-review` 接口组（6 个接口）
- **Base_Database**：新增迁移 026 说明、`tiktok_review_configs` 表

---

## 七、测试计划

### 后端集成测试 `tests/integration/routers/test_operator_tiktok_review.py`

| 用例 | 说明 |
|------|------|
| `test_generate_streams_text` | SSE 返回文本流，写 ai_call_logs |
| `test_generate_no_config` | 配置未激活 → 503 |
| `test_save_output` | 保存报告，返回 output id |
| `test_outputs_list` | 列表分页，按时间降序 |
| `test_export_word` | 返回 docx 二进制，Content-Type 正确 |
| `test_admin_get_config` | 读配置正常 |
| `test_admin_update_config` | 写配置，读回验证 |
| `test_operator_cannot_access_admin` | 403 |

覆盖率目标：`operator_tiktok_review.py` ≥ 70%，`admin_tiktok_review.py` ≥ 70%。

### 前端单元测试 `src/__tests__/unit/api/tiktokReview.test.ts`

| 用例 | 说明 |
|------|------|
| `save 成功` | mock 返回 output id |
| `save 失败` | 非 200 抛错 |
| `outputs 列表` | 返回数组 |
| `exportWord 触发下载` | Blob 处理正确 |
| `getConfig` | 返回 config 对象 |
| `updateConfig` | POST 参数正确 |

---

## 八、迁移检查清单（DoD）

- [ ] 迁移红线 1：运营端入口在「创作中心」
- [ ] 迁移红线 2：报告进产出中心
- [ ] 迁移红线 3：AI 走 yunwu adapter，不自直连
- [ ] 迁移红线 4：Prompt + 模型管理端可配
- [ ] 迁移红线 5：纳入管理端功能配置
- [ ] 迁移红线 6：AI 调用写 ai_call_logs
- [ ] 契约文档更新（Base_API + Base_Database）
- [ ] 后端测试通过，覆盖率 ≥ 70%
- [ ] 前端测试通过
- [ ] 全量回归（其他工具未被改坏）
- [ ] README 更新
- [ ] PM 记忆更新
