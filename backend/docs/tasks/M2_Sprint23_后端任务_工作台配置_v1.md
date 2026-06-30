# M2 Sprint23 后端任务 — 红人工作台配置（KOL Workspace Config）v1

> 编写时间：2026-06-30
> 分支：`feature/kol-workspace`
> 需求文档：`docs/pm/M2_Sprint23_红人工作台配置_需求文档.md`

---

## 一、任务范围

| # | 内容 |
|---|------|
| 1 | Migration 046：`kol_workspace_configs` 表 |
| 2 | ORM 模型：`KolWorkspaceConfig` |
| 3 | 服务层：`app/services/workspace_prompt.py`（`resolve_prompt`） |
| 4 | 管理端 Router：`admin_kol_workspace.py`（GET/PUT） |
| 5 | main.py 注册 + conftest.py 更新 |
| 6 | 8 个 AI 模块 router 接入 resolve_prompt |
| 7 | 集成测试 |

---

## 二、Migration 046

文件：`backend/migrations/046_kol_workspace_configs.sql`

```sql
-- kol_workspace_configs：红人工作台个性化配置（Sprint 23）
CREATE TABLE IF NOT EXISTS kol_workspace_configs (
    id               BIGSERIAL PRIMARY KEY,
    kol_id           BIGINT NOT NULL UNIQUE REFERENCES kols(id) ON DELETE CASCADE,
    enabled_tabs     JSONB NOT NULL DEFAULT
        '["dashboard","persona","references","products","qianchuan-writer",
          "seeding-writer","persona-writer","livestream-writer","livestream-review",
          "values-writer","script-review","retrospective"]',
    prompt_overrides JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kol_workspace_configs_kol_id ON kol_workspace_configs(kol_id);
CREATE TRIGGER trg_kol_workspace_configs_updated
    BEFORE UPDATE ON kol_workspace_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 三、ORM 模型

文件：`app/models/kol_workspace_config.py`

```python
from sqlalchemy import TIMESTAMP, BigInteger, Column, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base

class KolWorkspaceConfig(Base):
    __tablename__ = "kol_workspace_configs"
    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    kol_id           = Column(BigInteger, ForeignKey("kols.id", ondelete="CASCADE"), nullable=False, unique=True)
    enabled_tabs     = Column(JSONB, nullable=False, default=list)
    prompt_overrides = Column(JSONB, nullable=False, default=dict)
    created_at       = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at       = Column(TIMESTAMP(timezone=True), server_default=func.now())
```

注册到 `app/models/__init__.py`。

---

## 四、服务层：resolve_prompt

文件：`app/services/workspace_prompt.py`

```python
async def resolve_prompt(
    kol_id: int | None,
    tool_code: str,
    prompt_key: str,
    db: AsyncSession,
) -> str | None:
    """
    查询红人专属 Prompt。有配置且非空则返回，否则返回 None（调用方 fallback 全局）。
    kol_id 为 None 时直接返回 None。
    """
    if not kol_id:
        return None
    row = (await db.execute(
        select(KolWorkspaceConfig).where(KolWorkspaceConfig.kol_id == kol_id)
    )).scalar_one_or_none()
    if not row:
        return None
    overrides = row.prompt_overrides or {}
    value = (overrides.get(tool_code) or {}).get(prompt_key)
    return value if value and value.strip() else None
```

---

## 五、管理端 Router

文件：`app/routers/admin_kol_workspace.py`
前缀：`/admin/kols`

### 5.1 GET `/{kol_id}/workspace-config`

鉴权：admin 或 operator（operator 只读，供工作台读取 enabled_tabs）。

逻辑：
1. 查 `kol_workspace_configs` WHERE kol_id
2. 不存在时返回默认值（全部 tab 开启，prompt_overrides={}）
3. 同时查 8 个全局 prompt 配置表，拼入 `global_prompts`

```json
// Response data
{
  "kol_id": 1,
  "enabled_tabs": ["dashboard", "persona", ...],
  "prompt_overrides": {},
  "global_prompts": {
    "qianchuan-writer":  { "system_prompt": "..." },
    "persona-writer":    { "evaluation_prompt": "...", "analysis_prompt": "...", "writing_prompt": "...", "iteration_prompt": "..." },
    "seeding-writer":    { "sp_system": "...", "parse_product": "...", "structure_analysis": "...", "ai_recommend": "...", "writing": "...", "iteration": "..." },
    "livestream-writer": { "system_prompt": "..." },
    "livestream-review": { "with_excel_prompt": "...", "without_excel_prompt": "..." },
    "values-writer":     { "extract_values_prompt": "...", "emotion_direction_prompt": "...", "writing_prompt": "...", "iteration_prompt": "..." },
    "script-review":     { "direct_prompt": "...", "value_prompt": "..." },
    "retrospective":     { "system_prompt": "..." }
  }
}
```

### 5.2 PUT `/{kol_id}/workspace-config`

鉴权：admin。

逻辑：UPSERT kol_workspace_configs，写 OperationLog（action=`admin_update_kol_workspace_config`）。

Request Body：
```json
{
  "enabled_tabs": ["dashboard", "persona", "qianchuan-writer"],
  "prompt_overrides": {
    "qianchuan-writer": { "system_prompt": "..." }
  }
}
```

---

## 六、8 个 AI 模块接入 resolve_prompt

### 6.1 改动原则

- 有 kol_id 的模块：在加载全局 Prompt 之后，调 `resolve_prompt(kol_id, tool_code, prompt_key, db)` 尝试覆盖
- 没有 kol_id 的模块：在 Request body 增加 `kol_id: int | None = None`（可选），前端从工作台上下文注入

### 6.2 各模块改动点

#### 千川仿写（operator_qianchuan_writer.py）
- 端点：`POST /chat`
- `ChatRequest` 增加 `kol_id: int | None = None`
- prompt 覆盖点：`system_prompt`（`qianchuan-writer`）

#### 人设仿写（operator_persona_writer.py）
- 端点：`POST /evaluate-opening`、`/analyze-structure`、`/chat`
- `EvaluateOpeningRequest`、`AnalyzeStructureRequest`、`ChatRequest` 各增加 `kol_id: int | None = None`
- prompt 覆盖点：`evaluation_prompt`、`analysis_prompt`、`writing_prompt`/`iteration_prompt`（按 scene）

#### 种草仿写（operator_seeding_writer.py）
- 端点：`POST /products/extract-selling-points`（kol_id 已有 or 新增）、`/analyze-structure`（新增）、`/ai-recommend`（新增）、`/chat`（新增）
- 各 Request 增加 `kol_id: int | None = None`
- prompt 覆盖点：`sp_system`、`structure_analysis`、`ai_recommend`、`writing`/`iteration`（按 scene）

#### 直播仿写（operator_livestream_writer.py）
- 端点：`POST /chat`
- `ChatRequest` 增加 `kol_id: int | None = None`
- prompt 覆盖点：`system_prompt`（`livestream-writer`）
- 注：当前 ChatRequest 有 `systemPrompt` 字段（前端传入），覆盖顺序：per-KOL DB > 全局 DB > 前端传入

#### 直播复盘（operator_livestream_review.py）
- 端点：`POST /generate`
- `GenerateRequest` 增加 `kol_id: int | None = None`
- prompt 覆盖点：`with_excel_prompt`/`without_excel_prompt`（按 hasExcel）

#### 价值观仿写（operator_values_writer.py）
- 端点：`/extract-values`、`/emotion-direction`、`/write`、`/iterate`
- Request body 已有 `kol_id`，无需新增字段
- prompt 覆盖点：`extract_values_prompt`、`emotion_direction_prompt`、`writing_prompt`、`iteration_prompt`

#### 千川脚本预审（operator_script_review.py）
- 端点：`POST /review`
- `ReviewRequest` 增加 `kol_id: int | None = None`（工作台传入当前 kol_id，独立页面不传）
- prompt 覆盖点：`direct_prompt`/`value_prompt`（按 script_type）

#### 复盘（operator_retrospective.py）
- 端点：`POST /{kol_id}/retrospective/{session_id}/analyze`
- kol_id 已在 path 中，无需新增字段
- prompt 覆盖点：`system_prompt`（`retrospective`）

---

## 七、main.py 注册

```python
from app.routers import admin_kol_workspace
app.include_router(admin_kol_workspace.router, prefix="/api")
```

conftest.py：admin_kol_workspace 不直接导入 AsyncSessionLocal，无需加 patch。

---

## 八、集成测试

文件：`tests/integration/routers/test_admin_kol_workspace.py`

| # | 测试用例 |
|---|---------|
| 1 | test_no_token → 401 |
| 2 | test_operator_cannot_put → 403 |
| 3 | test_get_config_default（kol 无记录返回默认值） |
| 4 | test_put_config（upsert 成功 + OperationLog 写入） |
| 5 | test_get_config_after_put（PUT 后 GET 返回最新值） |
| 6 | test_put_partial_prompt_overrides（只覆盖部分字段，其他字段保持 null） |

各 AI 模块现有测试：验证 kol_id=None 时走全局 Prompt（回归），kol_id 有值时优先用覆盖 Prompt（新增 mock 测试）。

---

## 九、验收口径

1. GET 返回 global_prompts（从各全局 config 表聚合），无 kol 配置时 prompt_overrides={}
2. PUT 后再 GET 返回最新值
3. values-writer（已有 kol_id 字段）无需改动 Request body 即可覆盖
4. 后端全量测试通过（新增用例 + 原有不回归）
