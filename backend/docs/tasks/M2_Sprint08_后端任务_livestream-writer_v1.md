# M2 Sprint 08 — 后端任务 · 直播脚本仿写（livestream-writer）迁移 v1

> 节点：B
> 创建日期：2026-06-15
> 依赖需求文档：`docs/pm/M2_Sprint08_livestream-writer_需求文档.md`

---

## 一、交付文件清单

| 文件 | 动作 |
|------|------|
| `backend/migrations/021_livestream_writer.sql` | 新增 |
| `backend/app/routers/operator_livestream_writer.py`（GET /config） | 新增（实时拉取 Prompt，供前端 LivestreamWriterPage 使用） |
| `backend/app/models/livestream_writer.py` | 新增 |
| `backend/app/services/file_parser.py` | 追加函数 |
| `backend/app/routers/operator_livestream_writer.py` | 新增 |
| `backend/app/routers/admin_livestream_writer.py` | 新增 |
| `backend/app/main.py` | 注册两个 router |
| `backend/tests/unit/test_file_parser_livestream.py` | 新增 |
| `backend/tests/integration/test_livestream_writer.py` | 新增 |

---

## 二、迁移文件 `021_livestream_writer.sql`

```sql
-- 1. 配置表
CREATE TABLE livestream_writer_configs (
  id            SERIAL PRIMARY KEY,
  config_key    VARCHAR(50)   NOT NULL UNIQUE,
  ai_model_id   INT           REFERENCES ai_models(id) ON DELETE SET NULL,
  system_prompt TEXT,
  is_active     BOOLEAN       NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_livestream_writer_configs_updated
  BEFORE UPDATE ON livestream_writer_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 2. 初始配置（两条：首次生成 / 多轮迭代）
INSERT INTO livestream_writer_configs (config_key, system_prompt, is_active) VALUES
('generate', '<首次生成 System Prompt 原文>', true),
('iterate',  '<多轮迭代 System Prompt 原文>', true);

-- 3. 注册工具
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
  'livestream-writer', '直播脚本仿写', '内容创作',
  '选择达人 + 上传产品卖点卡 + 上传对标直播间文案，AI 生成完整7模块开播方案，支持多轮对话修改，导出 .txt',
  'online',
  '["AI生成","直播","脚本","仿写","txt"]'::jsonb,
  (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM workspace_tools)
)
ON CONFLICT (tool_code) DO NOTHING;
```

---

## 三、Model `app/models/livestream_writer.py`

参照 `app/models/tiktok_writer.py` 的 `TiktokWriterConfig`，定义 `LivestreamWriterConfig`：

```python
class LivestreamWriterConfig(Base):
    __tablename__ = "livestream_writer_configs"
    id           = Column(Integer, primary_key=True)
    config_key   = Column(String(50), nullable=False, unique=True)
    ai_model_id  = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    system_prompt = Column(Text, nullable=True)
    is_active    = Column(Boolean, nullable=False, default=True)
    created_at   = Column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMPTZ, nullable=False, server_default=func.now())
```

---

## 四、`file_parser.py` 追加函数

在文件末尾追加 `parse_livestream_writer_file`：

- 格式支持：`.txt / .md / .docx / .pages`，不支持 `.pdf`（返回提示文字）
- `.pages` 解析：同 `_parse_pages_qianchuan_review`（含日历噪音过滤），**复用同一私有函数**
- 其他格式：抛 `ValueError`

```python
async def parse_livestream_writer_file(file: UploadFile) -> str:
    """livestream-writer 专用文件解析。不支持 .pdf，其余同 qianchuan-review 版。"""
    ...
    elif ext == "pdf":
        return "[暂不支持 PDF 格式，请转为 .docx 或 .txt 后上传]"
    elif ext == "pages":
        return _parse_pages_qianchuan_review(content_bytes)  # 复用，逻辑等价
    ...
```

---

## 五、`operator_livestream_writer.py` 路由

前缀：`/tools/livestream-writer`，需要 operator / admin 角色。

### 5.1 GET `/config`

返回前端渲染所需的两条 Prompt + 绑定模型：

```python
@router.get("/config")
async def get_config(db, current_user):
    generate_cfg = await _get_lw_config("generate", db)
    iterate_cfg  = await _get_lw_config("iterate",  db)
    model_id = await _resolve_lw_model(generate_cfg, db)
    return success_response(data={
        "generate_prompt": generate_cfg.system_prompt or "",
        "iterate_prompt":  iterate_cfg.system_prompt or "",
        "model_id": model_id,
    })
```

**前端行为**：进入 LivestreamWriterPage 时调一次此接口，把 prompt 存入 state，chat 时直接用（不再硬编码）。

### 5.2 GET `/kols/personas`

```python
SELECT id, name, persona, content_plan
FROM kols
WHERE content_plan IS NOT NULL AND persona IS NOT NULL AND deleted_at IS NULL
ORDER BY name
```

返回：`{ "personas": [{ "name", "soul"（=persona）, "contentPlan"（=content_plan） }] }`

### 5.2 POST `/parse-file`

调用 `parse_livestream_writer_file`，返回 `{ "text": "...", "filename": "..." }`（**不是标准信封**，与 qianchuan-review 保持一致）。

写 `OperationLog`（action=`"livestream_parse_file"`）。

### 5.3 POST `/chat`

```python
class ChatRequest(BaseModel):
    messages: list[dict]
    systemPrompt: str
    model: str = "claude-opus-4-6-thinking"
    createJob: bool = False
    jobContext: dict | None = None
```

- 流式生成：同 tiktok-writer 模式，用 `yunwu_adapter.chat_stream`
- **重试策略**：429 时最多 5 次，delays = `[5, 10, 15, 20, 25]`（比 tiktok-writer 更激进）
- **BackgroundTask**（仅 createJob=true）：
  1. 写 `task_jobs`（tool_code=`'livestream-writer'`，input_payload 含 productName/personaName/spOrder/refLength）
  2. 写 `outputs`（title=`"开播方案 · {productName} · {personaName}"`，content=完整内容，word_count=去空格字符数）
- **AiCallLog** 由 yunwu adapter 自动写，router 层不重复写（#6 红线）

---

## 六、`admin_livestream_writer.py` 路由

前缀：`/admin/livestream-writer`，需要 admin 角色。

```
GET  /configs          列出所有 livestream_writer_configs
PUT  /configs/{key}    更新指定 key 的 system_prompt / ai_model_id / is_active
```

写 `OperationLog`（PUT 接口，action=`"update_livestream_writer_config"`）。

---

## 七、main.py 注册

```python
from app.routers.operator_livestream_writer import router as operator_livestream_writer_router
from app.routers.admin_livestream_writer import router as admin_livestream_writer_router

app.include_router(operator_livestream_writer_router, prefix="/api")
app.include_router(admin_livestream_writer_router, prefix="/api")
```

**同时**：若 `operator_livestream_writer.py` 中使用了 `AsyncSessionLocal`（BackgroundTask），必须在 `tests/conftest.py` 的 `_SESSION_LOCAL_PATCH_TARGETS` 中注册（#7 红线）。

---

## 八、测试清单

### 单元测试（file_parser）

| 测试场景 | 期望 |
|---------|------|
| .txt 文件 | 正常返回文本 |
| .md 文件 | 正常返回文本 |
| .docx 文件（正常） | 正常返回段落文本 |
| .pages 文件（mock snappy） | 正常返回中文片段，过滤日历噪音 |
| .pdf 文件 | 返回提示字符串 |
| 不支持格式（.csv） | 抛 ValueError |
| .pages 文件（BadZipFile） | 返回格式异常提示 |

### 集成测试（router）

| 接口 | 测试场景 |
|------|---------|
| GET /kols/personas | 无 JWT 返回 401；有 JWT 返回 personas 列表（含 content_plan 和 persona 均非空） |
| POST /parse-file | 无 JWT 401；.txt 正常；.pdf 返回提示；不支持格式 400 |
| POST /chat | 无 JWT 401；messages 空 400；systemPrompt 空 400；正常返回 text/plain 流 |
| GET /admin/configs | 非 admin 403；admin 返回两条配置 |
| PUT /admin/configs/{key} | 正常更新；key 不存在 404 |

---

## 九、开发红线检查清单

- [ ] #1 非流式接口返回标准信封（parse-file 和 kols/personas 例外，同 qianchuan-review）
- [ ] #2 parse-file 和 admin PUT 接口写 OperationLog
- [ ] #4 无接口/表结构变更需同步 Base_API / Base_Database
- [ ] #6 AiCallLog 不在 router 写
- [ ] #7 若 router 用了 AsyncSessionLocal，在 conftest.py 注册
