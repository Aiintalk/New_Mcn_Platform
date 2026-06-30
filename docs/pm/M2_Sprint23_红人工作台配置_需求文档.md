# M2 Sprint 23 — 红人工作台配置（KOL Workspace Config）需求文档

> **版本**：v1
> **编写时间**：2026-06-30
> **作者**：MCN_PM_Agent
> **分支**：`feature/kol-workspace`
> **状态**：📝 待开发

---

## 一、背景与目标

### 1.1 背景

当前红人工作台（KolWorkspacePage）对所有红人展示相同的 13 个 tab，所有 AI 模块使用全局统一的 Prompt 配置。业务侧需要能针对不同红人：
1. 定制工作台显示哪些功能模块（tab）
2. 针对特定红人配置专属 AI Prompt，覆盖全局默认值

### 1.2 目标

| # | 目标 | 验收 |
|---|------|------|
| 1 | 管理员可按红人开关工作台 tab | 进入工作台只显示已启用的 tab |
| 2 | 管理员可为每个红人配置各 AI 模块的专属 Prompt | AI 调用时优先使用红人专属 Prompt |
| 3 | 红人未配置时 fallback 全局配置 | 新红人无需配置即可正常使用 |
| 4 | 配置入口在管理端红人列表 | 每行有「工作台配置」按钮 |

---

## 二、范围

### 2.1 在范围

| # | 改动 | 说明 |
|---|------|------|
| 1 | DB Migration 046 | 新建 `kol_workspace_configs` 表 |
| 2 | ORM 模型 | `KolWorkspaceConfig` |
| 3 | 后端服务 | `workspace_prompt.py` — `resolve_prompt()` 公共函数 |
| 4 | 管理端 API | GET/PUT `/api/admin/kols/{kol_id}/workspace-config` |
| 5 | 8 个 AI 模块接入 | 调用时优先查红人专属 Prompt |
| 6 | 前端管理端配置页 | 新建 `KolWorkspaceConfigPage.tsx` |
| 7 | 管理端红人列表 | 加「工作台配置」入口按钮 |
| 8 | 前端工作台 | 按 `enabled_tabs` 过滤左侧导航 |

### 2.2 不在范围

- 运营端修改工作台配置（仅管理员可改）
- 按红人配置 AI 模型（只覆盖 Prompt，模型仍用全局配置）
- 千川成片预审（Sprint 23 本体，film-review tab disabled 暂不处理）

---

## 三、数据模型

### 3.1 kol_workspace_configs 表

```sql
id              BIGSERIAL PK
kol_id          BIGINT NOT NULL UNIQUE FK kols(id) ON DELETE CASCADE
enabled_tabs    JSONB NOT NULL DEFAULT '[全部 12 个 tab]'
prompt_overrides JSONB NOT NULL DEFAULT '{}'
created_at      TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW()（触发器自动更新）
```

`enabled_tabs` 格式（有序数组）：
```json
["dashboard","persona","references","products",
 "qianchuan-writer","seeding-writer","persona-writer",
 "livestream-writer","livestream-review","values-writer",
 "script-review","retrospective"]
```

`prompt_overrides` 格式：
```json
{
  "qianchuan-writer": { "system_prompt": "专属 Prompt..." },
  "persona-writer": {
    "evaluation_prompt": "...",
    "analysis_prompt": "...",
    "writing_prompt": "...",
    "iteration_prompt": "..."
  },
  "seeding-writer": {
    "sp_system": "...", "parse_product": "...",
    "structure_analysis": "...", "ai_recommend": "...",
    "writing": "...", "iteration": "..."
  },
  "livestream-writer": { "system_prompt": "..." },
  "livestream-review": { "with_excel_prompt": "...", "without_excel_prompt": "..." },
  "values-writer": {
    "extract_values_prompt": "...", "emotion_direction_prompt": "...",
    "writing_prompt": "...", "iteration_prompt": "..."
  },
  "script-review": { "direct_prompt": "...", "value_prompt": "..." },
  "retrospective": { "system_prompt": "..." }
}
```

字段为 `null` 或空字符串 = 不覆盖，fallback 全局。

---

## 四、接口设计

### 4.1 GET `/api/admin/kols/{kol_id}/workspace-config`

返回该红人的配置，含各模块的全局默认值（供前端参考展示）。

Response `data`：
```json
{
  "kol_id": 1,
  "enabled_tabs": ["dashboard", "persona", ...],
  "prompt_overrides": { ... },
  "global_prompts": {
    "qianchuan-writer": { "system_prompt": "全局 Prompt..." },
    ...
  }
}
```

### 4.2 PUT `/api/admin/kols/{kol_id}/workspace-config`

Upsert 整条配置，写 OperationLog（action=`admin_update_kol_workspace_config`）。

Request Body：
```json
{
  "enabled_tabs": ["dashboard", "persona", "qianchuan-writer"],
  "prompt_overrides": {
    "qianchuan-writer": { "system_prompt": "专属 Prompt..." }
  }
}
```

### 4.3 运营端读取（复用管理端接口）

运营端 `KolWorkspacePage` 也调用此接口读取 `enabled_tabs`（只读，无需单独接口）。

---

## 五、AI 模块 Prompt 覆盖逻辑

### 5.1 resolve_prompt 服务

```python
# app/services/workspace_prompt.py
async def resolve_prompt(
    kol_id: int | None,
    tool_code: str,
    prompt_key: str,
    db: AsyncSession
) -> str | None:
    """
    返回该红人的专属 Prompt，无配置时返回 None（调用方 fallback 全局默认）。
    kol_id 为 None 时直接返回 None。
    """
```

### 5.2 各模块需改动的端点 + prompt_key 对照

| 模块 | tool_code | 端点 | prompt_key | kol_id 来源 |
|------|-----------|------|------------|------------|
| 千川仿写 | `qianchuan-writer` | POST /chat | `system_prompt` | body.persona_id → 查 kol_id |
| 人设仿写 | `persona-writer` | POST /evaluate-opening | `evaluation_prompt` | body 新增 `kol_id` |
| 人设仿写 | `persona-writer` | POST /analyze-structure | `analysis_prompt` | body 新增 `kol_id` |
| 人设仿写 | `persona-writer` | POST /chat | `writing_prompt`/`iteration_prompt` | body 新增 `kol_id` |
| 种草仿写 | `seeding-writer` | POST /products/extract-selling-points | `sp_system` | body 新增 `kol_id` |
| 种草仿写 | `seeding-writer` | POST /analyze-structure | `structure_analysis` | body 中已有 |
| 种草仿写 | `seeding-writer` | POST /ai-recommend | `ai_recommend` | body 中已有 |
| 种草仿写 | `seeding-writer` | POST /chat | `writing`/`iteration` | body 中已有 |
| 直播仿写 | `livestream-writer` | POST /chat | `system_prompt` | body 新增 `kol_id` |
| 直播复盘 | `livestream-review` | POST /generate | `with_excel_prompt`/`without_excel_prompt` | body 新增 `kol_id` |
| 价值观仿写 | `values-writer` | POST /extract-values、/emotion-direction、/write、/iterate | 各自 prompt_key | body 已有 `kol_id` |
| 千川脚本预审 | `script-review` | POST /review | `direct_prompt`/`value_prompt` | body 新增 `kol_id`（optional） |
| 复盘 | `retrospective` | POST /{id}/analyze | `system_prompt` | path 已有 `kol_id` |

> **kol_id 为 None 时**（script-review 从非工作台入口调用）：直接使用全局 Prompt，不查 override。

---

## 六、前端交互

### 6.1 管理端配置页（新建）

路由：`/admin/kols/:kol_id/workspace-config`

布局：
```
顶部：← 返回红人列表 | 红人名称 + 头像
├── Section 1：模块开关
│   ├── 每个 tab 一行：图标 + 名称 + Toggle 开关
│   └── 「全选/全不选」快捷操作
└── Section 2：AI Prompt 覆盖
    ├── 每个支持覆盖的模块（8个）一个折叠面板（Collapse）
    │   ├── 标题：模块名 + Badge（已覆盖 N 项 / 全局默认）
    │   └── 展开后：各 prompt_key 对应 TextArea
    │       └── 下方灰色小字展示「当前全局默认值」
    └── 保存按钮（全局一个，批量提交）
```

### 6.2 管理端红人列表入口

在 `KolsPage`（管理端）每行操作列加「工作台配置」按钮，点击跳转 `/admin/kols/{kol_id}/workspace-config`。

### 6.3 运营端工作台 tab 过滤

`KolWorkspacePage.tsx` 加载时：
1. 调 GET `/api/admin/kols/{kol_id}/workspace-config` 读取 `enabled_tabs`
2. 按此列表过滤左侧 `NAV_ITEMS`，未配置的 kol 显示全部 tab（默认值）
3. 加载失败时降级显示全部 tab（不影响正常使用）

---

## 七、验收标准

| # | 验收项 |
|---|--------|
| 1 | 管理端红人列表有「工作台配置」入口 |
| 2 | 配置页可开关任意 tab，保存后工作台立即生效 |
| 3 | 配置页可为每个 AI 模块填写专属 Prompt，空值不覆盖全局 |
| 4 | 全局默认 Prompt 在字段下方可见（灰色提示） |
| 5 | 新建红人未配置时工作台显示全部 tab、使用全局 Prompt |
| 6 | 后端全量回归通过（新增用例 + 原有通过） |

---

## 八、文档索引

| 文件 | 说明 |
|------|------|
| `backend/docs/tasks/M2_Sprint23_后端任务_工作台配置_v1.md` | 后端实现细节 |
| `frontend/docs/tasks/M2_Sprint23_前端任务_工作台配置_v1.md` | 前端实现细节 |
| `backend/docs/base/MCN_M2_Base_API.md` §29 | 接口契约（开发完成后补） |
| `backend/docs/base/MCN_M2_Base_Database.md` §36 | 数据库契约（开发完成后补） |
