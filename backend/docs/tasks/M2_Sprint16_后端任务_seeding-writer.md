# M2 Sprint 16 — 后端任务：种草内容仿写（seeding-writer）

> 状态：**待派 subagent 实施**
> 对应需求文档：`docs/pm/M2_Sprint16_seeding-writer_需求文档.md`
> 对应分支：`migrate/seeding-writer`
> 参照样板：`backend/docs/tasks/M2_Sprint15_后端任务_persona-writer_v1.md`（最接近的迁移）

---

## 一、范围（本次后端任务）

涵盖种草内容仿写工具迁移的所有后端工作：
- Migration 033（3 张表：configs + products + references + 6 种子 Prompt + workspace_tools status='online'）
- 3 个 ORM 模型 + 注册 `__init__.py`
- Prompt 渲染 service（14 占位符）
- 文档解析 service（PDF/DOCX/XLSX/PPTX/TXT）
- requirements.txt 加 4 个解析库（pypdf / python-docx / openpyxl / python-pptx）
- operator_seeding_writer.py **20 个接口**
- admin_seeding_writer.py 2 个接口
- main.py + conftest.py 注册
- 单测 + 集测全绿
- 全量回归通过

---

## 二、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | Migration 033（3 张表 + 6 种子 Prompt + workspace_tools online）| `backend/migrations/033_seeding_writer.sql` | ⏳ |
| B2 | ORM 模型 SeedingWriterConfig | `backend/app/models/seeding_writer.py`（class SeedingWriterConfig）| ⏳ |
| B3 | ORM 模型 SeedingWriterProduct | 同上（class SeedingWriterProduct）| ⏳ |
| B4 | ORM 模型 SeedingWriterReference | 同上（class SeedingWriterReference）| ⏳ |
| B5 | 注册到 `models/__init__.py` | `backend/app/models/__init__.py` | ⏳ |
| B6 | Prompt 渲染 service（14 占位符）| `backend/app/services/seeding_writer_prompt.py` | ⏳ |
| B7 | 文档解析 service | `backend/app/services/document_parser.py` | ⏳ |
| B8 | requirements.txt 加 4 个解析库 | `backend/requirements.txt` | ⏳ |
| B9 | operator router 20 接口 | `backend/app/routers/operator_seeding_writer.py` | ⏳ |
| B10 | admin router 2 接口 | `backend/app/routers/admin_seeding_writer.py` | ⏳ |
| B11 | main.py 注册两个 router | `backend/app/main.py` | ⏳ |
| B12 | conftest.py 加 AsyncSessionLocal patch（如需）| `backend/tests/conftest.py` | ⏳ |
| B13 | 单测 + 集测 | 见下表 | ⏳ |
| B14 | 任务文档 | 本文件 | ⏳ |

---

## 三、Migration 033 详细设计

**文件**：`backend/migrations/033_seeding_writer.sql`

```sql
-- ========== 1. seeding_writer_configs ==========
CREATE TABLE IF NOT EXISTS seeding_writer_configs (
  id                     BIGSERIAL PRIMARY KEY,
  config_key             VARCHAR(64) NOT NULL UNIQUE,
  sp_system_prompt       TEXT,
  parse_product_prompt   TEXT,
  structure_analysis_prompt TEXT,
  ai_recommend_prompt    TEXT,
  writing_prompt         TEXT,
  iteration_prompt       TEXT,
  light_model_id         BIGINT,
  heavy_model_id         BIGINT,
  is_active              BOOLEAN NOT NULL DEFAULT TRUE,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========== 2. seeding_writer_products（公司共享） ==========
CREATE TABLE IF NOT EXISTS seeding_writer_products (
  id                        BIGSERIAL PRIMARY KEY,
  name                      TEXT NOT NULL,
  category                  TEXT,
  price                     TEXT,
  selling_points            TEXT,
  target_audience           TEXT,
  scenario                  TEXT,
  medical_aesthetic_anchor  TEXT,
  created_by                BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at                TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_seeding_writer_products_name       ON seeding_writer_products(name) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_seeding_writer_products_created_by ON seeding_writer_products(created_by);

-- ========== 3. seeding_writer_references（达人维度共享） ==========
CREATE TABLE IF NOT EXISTS seeding_writer_references (
  id          BIGSERIAL PRIMARY KEY,
  kol_id      BIGINT REFERENCES kols(id) ON DELETE SET NULL,
  title       TEXT NOT NULL,
  content     TEXT NOT NULL,
  type        VARCHAR(32),
  source      VARCHAR(32),
  likes       INT,
  douyin_url  TEXT,
  created_by  BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_seeding_writer_references_kol_id     ON seeding_writer_references(kol_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_seeding_writer_references_created_by ON seeding_writer_references(created_by);

-- ========== 4. 种子 6 个 Prompt（从旧版 page.tsx 提取） ==========
INSERT INTO seeding_writer_configs (config_key, sp_system_prompt, parse_product_prompt, structure_analysis_prompt, ai_recommend_prompt, writing_prompt, iteration_prompt, is_active)
VALUES ('default',
  '<<卖点提取 spSystemPrompt 全文（旧版 page.tsx 第 220-239 行）>>',
  '<<文档解析 systemPrompt 全文（旧版 parse-product/route.ts 第 73-94 行）>>',
  '<<结构拆解 systemPrompt 全文（旧版 page.tsx 第 476-488 行）>>',
  '<<AI 推荐 systemPrompt 全文（旧版 page.tsx 第 513-549 行）>>',
  '<<写作 systemPrompt 全文（旧版 page.tsx 第 565-618 行），${var} 改 {{var}}>>',
  '<<迭代 systemPrompt 全文（旧版 page.tsx 第 667-690 行），${var} 改 {{var}}>>',
  TRUE
)
ON CONFLICT (config_key) DO NOTHING;

-- ========== 5. workspace_tools ==========
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, sort_order)
VALUES ('seeding-writer', '种草内容仿写', 'writer', '基于达人 + 产品 + 对标视频的种草短视频脚本仿写', 'online', 5)
ON CONFLICT (tool_code) DO UPDATE SET status='online', tool_name=EXCLUDED.tool_name;
```

---

## 四、ORM 模型

### 4.1 SeedingWriterConfig（参照 PersonaWriterConfig）

**文件**：`backend/app/models/seeding_writer.py`

字段对齐 migration 表结构，类型映射：
- BIGSERIAL → BigInteger + primary_key=True
- TEXT → Text
- VARCHAR(64) → String(64)
- BOOLEAN → Boolean
- TIMESTAMPTZ → DateTime(timezone=True)
- server_default=func.now() / func.now() onupdate

### 4.2 SeedingWriterProduct

字段：id / name / category / price / selling_points / target_audience / scenario / medical_aesthetic_anchor / created_by / created_at / updated_at / deleted_at（软删）

### 4.3 SeedingWriterReference

字段：id / kol_id / title / content / type / source / likes / douyin_url / created_by / created_at / updated_at / deleted_at（软删）

### 4.4 注册 __init__.py

```python
from app.models.seeding_writer import (
    SeedingWriterConfig,
    SeedingWriterProduct,
    SeedingWriterReference,
)
```

---

## 五、Prompt 渲染 service

**文件**：`backend/app/services/seeding_writer_prompt.py`（参照 `persona_writer_prompt.py`）

### 5.1 render_prompt 函数签名

```python
def render_prompt(
    template: str,
    *,
    name: str = "",
    soul: str = "",
    content_plan: str = "",
    product_name: str = "",
    product_category: str = "",
    product_price: str = "",
    product_selling_points: str = "",
    product_target_audience: str = "",
    product_scenario: str = "",
    references: str = "",
    transcript: str = "",
    structure_analysis: str = "",
    topic: str = "",
    raw_text: str = "",
) -> str:
    """
    渲染 Prompt 模板，支持 14 个占位符：
      {{name}} {{soul}} {{content_plan}}
      {{product_name}} {{product_category}} {{product_price}}
      {{product_selling_points}} {{product_target_audience}} {{product_scenario}}
      {{references}} {{transcript}} {{structure_analysis}} {{topic}} {{raw_text}}
    """
```

### 5.2 实现要点

- 单次正则一次性替换（避免 soul / content 内容含 `{{xxx}}` 时二次替换）
- 正则：`re.compile(r"\{\{\s*(name|soul|content_plan|product_name|...|raw_text)\s*\}\}")`
- 用 lambda 匹配 key 拿值（不用 chained .replace）
- 缺失值 fallback 空字符串

### 5.3 14 占位符使用映射

| Prompt | 用到的占位符 |
|--------|-------------|
| sp_system_prompt | `{{raw_text}}` |
| parse_product_prompt | （固定 JSON 输出，无占位符）|
| structure_analysis_prompt | `{{transcript}}` |
| ai_recommend_prompt | `{{name}} {{soul}} {{content_plan}} {{product_selling_points}} {{product_target_audience}} {{references}} {{transcript}}` |
| writing_prompt | `{{name}} {{soul}} {{content_plan}} {{product_name}} {{product_category}} {{product_price}} {{product_selling_points}} {{product_target_audience}} {{product_scenario}} {{references}} {{transcript}} {{structure_analysis}} {{topic}}` |
| iteration_prompt | 同 writing（去掉 topic）|

---

## 六、文档解析 service

**文件**：`backend/app/services/document_parser.py`

### 6.1 函数签名

```python
async def parse_files_to_text(files: list[UploadFile]) -> str:
    """
    解析多个上传文件，合并为单一文本（截断 8000 字符）。
    按扩展名分流：
      .pdf  → pypdf.PdfReader
      .docx → python-docx.Document
      .xlsx/.xls → openpyxl.load_workbook
      .pptx → python-pptx.Presentation
      .txt/.md → utf-8 直接读
    返回合并文本，每文件以 `=== 文件: xxx ===\n` 分隔。
    """
```

### 6.2 异常处理

- 单文件解析失败：log warning + 跳过，不影响其他文件
- 全部失败：抛 ValueError("无法从文件中提取有效文字内容")
- 文本过短（<10 字符）：抛 ValueError

### 6.3 库选型

| 扩展名 | 库 | 备注 |
|--------|-----|------|
| .pdf | pypdf | 纯 Python，无 snappy 依赖（旧版 livestream 踩过 snappy 坑）|
| .docx | python-docx | — |
| .xlsx/.xls | openpyxl | 只支持 .xlsx（.xls 老格式不支持，抛 ValueError 提示转 xlsx）|
| .pptx | python-pptx | — |
| .txt/.md | 标准库 | utf-8 读 |

---

## 七、operator_seeding_writer.py 详细设计

**文件**：`backend/app/routers/operator_seeding_writer.py`（参照 `operator_persona_writer.py` 模式）

```python
router = APIRouter(prefix="/tools/seeding-writer", tags=["seeding-writer"])

TOOL_CODE = "seeding-writer"
TOOL_NAME = "种草内容仿写"
DEFAULT_LIGHT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_HEAVY_MODEL = "claude-opus-4-6"
_RETRY_DELAYS = [2, 4, 6]
_PAGE_SIZE_ALLOWED = {10, 20, 50}
```

### 7.1 接口清单（20 个）

| # | 方法 | 路径 | 用途 | OperationLog |
|---|------|------|------|-------------|
| 1 | GET | `/kols/personas` | 达人下拉（同 persona-writer）| 否（只读）|
| 2 | GET | `/references` | 列出某达人素材（kol_id 参数）| 否 |
| 3 | POST | `/references` | 新增素材（粘贴文本）| **是** |
| 4 | POST | `/references/import-from-douyin` | 抖音链接导入素材（阻塞）| **是** |
| 5 | DELETE | `/references/{id}` | 软删素材 | **是** |
| 6 | GET | `/products` | 产品库列表（公司共享，分页）| 否 |
| 7 | POST | `/products` | 新建产品（公司共享）| **是** |
| 8 | PUT | `/products/{id}` | 更新产品 | **是** |
| 9 | DELETE | `/products/{id}` | 软删产品 | **是** |
| 10 | POST | `/products/parse-document` | 上传文档 AI 解析（multipart）| **是** |
| 11 | POST | `/products/extract-selling-points` | AI 卖点讨论（流式）| 否（流式）|
| 12 | POST | `/fetch-video` | 抖音链接解析（复用 tikhub）| **是** |
| 13 | POST | `/transcribe/submit` | 提交 ASR（download→OSS→submit）| **是** |
| 14 | POST | `/transcribe/poll` | 轮询 ASR 结果 | 否（高频）|
| 15 | POST | `/analyze-structure` | 结构拆解（流式，light）| 否（流式）|
| 16 | POST | `/ai-recommend` | AI 推荐角度（流式，light）| 否（流式）|
| 17 | POST | `/chat` | 写作+迭代（流式，heavy）| 否（流式，create_job 时 BackgroundTask 写）|
| 18 | POST | `/save-output` | 保存产出 | **是** |
| 19 | POST | `/export-word` | 导出 .docx | 否（StreamingResponse）|
| 20 | GET | `/outputs` | 历史记录（账号隔离）| 否 |

### 7.2 关键接口实现细节

#### POST /references/import-from-douyin（同步阻塞）

```python
async def import_from_douyin(body, db, current_user):
    # 1. fetch-video
    video = await tikhub_adapter.fetch_video_by_share_url(body.share_url, db)
    # 2. download play_url
    async with httpx.AsyncClient() as client:
        r = await client.get(video["play_url"], headers={"User-Agent": "...", "Referer": "https://www.douyin.com/"})
        buffer = r.content
    # 3. upload OSS + sign URL
    object_key = f"seeding-writer/references/{int(time.time())}.mp4"
    await oss_adapter.upload(buffer, object_key, "video/mp4")
    signed_url = oss_adapter.sign(object_key, expire=3600)
    # 4. ASR 同步阻塞（max 600s）
    transcript = await asr_adapter.transcribe(signed_url, db, user_id=current_user.id)
    # 5. 写表
    ref = SeedingWriterReference(kol_id=body.kol_id, title=video["title"], content=transcript, type=body.type, likes=video["digg_count"], source="抖音", douyin_url=body.share_url, created_by=current_user.id)
    db.add(ref); await db.flush()
    db.add(OperationLog(...)); await db.commit()
    return success_response(data={"id": ref.id, "title": ref.title, "content": ref.content})
```

#### POST /products/parse-document（multipart）

```python
@router.post("/products/parse-document")
async def parse_product_document(
    request: Request,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    # 1. 解析文本
    raw_text = await document_parser.parse_files_to_text(files)
    # 2. 调 AI（heavy 模型）+ parse_product_prompt
    config = await _get_config(db)
    model_id = await _resolve_model_id(config, db, is_heavy=True)
    # 3. chat（非流式，collect 完整 JSON）
    json_str = await _collect_chat(model_id, parse_product_prompt, raw_text, db, current_user.id)
    # 4. 解析 JSON
    product_info = _parse_product_json(json_str)
    product_info["_rawText"] = raw_text
    # 5. OperationLog
    db.add(OperationLog(action="seeding_writer_parse_product", ...))
    await db.commit()
    return success_response(data=product_info)
```

#### POST /transcribe/submit + /poll（分离）

```python
@router.post("/transcribe/submit")
async def submit_transcribe(body, db, current_user):
    # 1. download play_url
    buffer = await _download_video(body.play_url)
    # 2. upload OSS + sign
    object_key = f"seeding-writer/transcribe/{int(time.time())}.mp4"
    await oss_adapter.upload(buffer, object_key, "video/mp4")
    signed_url = oss_adapter.sign(object_key, expire=3600)
    # 3. submit ASR
    task_id = await asr_adapter.submit_transcription(signed_url, db, user_id=current_user.id)
    db.add(OperationLog(action="seeding_writer_transcribe_submit", ...))
    await db.commit()
    return success_response(data={"task_id": task_id, "expected_max_seconds": 600})

@router.post("/transcribe/poll")
async def poll_transcribe(body, db, current_user):
    r = await asr_adapter.query_transcription(body.task_id, db, user_id=current_user.id)
    status_text = r.get("StatusText", "")
    if status_text in ("RUNNING", "QUEUEING"):
        return success_response(data={"status": "processing"})
    if status_text == "SUCCESS":
        sentences = (r.get("Result") or {}).get("Sentences") or []
        text = "".join(s.get("Text", "") for s in sentences)
        return success_response(data={"status": "done", "text": text})
    raise HTTPException(502, detail={"code": "ASR_ERROR", "message": f"{r.get('StatusCode')} {status_text}"})
```

#### POST /chat（同 persona-writer，加 product_id + reference_ids）

```python
@router.post("/chat")
async def chat(body, db, current_user):
    # 1. 读 config + kol + product + references
    config = await _get_config(db)
    kol_name, kol_persona, kol_content_plan = await _get_kol(db, body.persona_id)
    product = await _get_product(db, body.product_id)
    references = await _get_references(db, body.reference_ids)
    references_text = "\n\n---\n\n".join(r.content for r in references)
    # 2. render_prompt
    if body.scene == "writing":
        system_prompt = render_prompt(config.writing_prompt, name=kol_name, ..., topic=body.topic)
    else:
        system_prompt = render_prompt(config.iteration_prompt, name=kol_name, ...)
    # 3. 流式 chat（同 persona-writer）
    ...
```

### 7.3 helpers（参照 persona-writer）

- `require_operator` — 同 persona-writer
- `_get_ip(request)` — 同 persona-writer
- `_get_config(db)` — 读 SeedingWriterConfig WHERE config_key='default' AND is_active=true
- `_resolve_model_id(config, db, is_heavy)` — 同 persona-writer
- `_get_kol(db, kol_id)` — 同 persona-writer
- `_get_product(db, product_id)` — 读 SeedingWriterProduct WHERE id AND deleted_at IS NULL
- `_get_references(db, reference_ids)` — 读 SeedingWriterReference WHERE id IN (...) AND deleted_at IS NULL

---

## 八、admin_seeding_writer.py

**文件**：`backend/app/routers/admin_seeding_writer.py`（参照 `admin_persona_writer.py`）

```python
class ConfigIn(BaseModel):
    sp_system_prompt: str | None = None
    parse_product_prompt: str | None = None
    structure_analysis_prompt: str | None = None
    ai_recommend_prompt: str | None = None
    writing_prompt: str | None = None
    iteration_prompt: str | None = None
    light_model_id: int | None = None
    heavy_model_id: int | None = None
    is_active: bool = True
```

接口：
- `GET /api/admin/seeding-writer/configs`
- `PUT /api/admin/seeding-writer/configs/{config_key}` — 写 OperationLog

---

## 九、main.py + conftest.py 注册

### 9.1 main.py

```python
from app.routers.operator_seeding_writer import router as operator_seeding_writer_router
from app.routers.admin_seeding_writer import router as admin_seeding_writer_router

app.include_router(operator_seeding_writer_router, prefix="/api")
app.include_router(admin_seeding_writer_router, prefix="/api")
```

### 9.2 conftest.py（如果流式接口用 AsyncSessionLocal）

参照 persona-writer 的处理方式：
- 检查 `operator_seeding_writer.py` 是否有 `async with AsyncSessionLocal()` 流式调用
- 如有，conftest 的 `_ASYNC_SESSION_LOCAL_PATCH_TARGETS` 加 `"app.routers.operator_seeding_writer"`（与 persona-writer 同列表）

---

## 十、测试覆盖

### 10.1 单元测试

| 文件 | 用例数 | 关键点 |
|------|--------|--------|
| `tests/unit/services/test_seeding_writer_prompt.py` | 16+ | 14 占位符逐个 + 缺失 fallback + 多次出现 + 真实模板 + 防 soul 含 `{{name}}` 二次替换 |
| `tests/unit/services/test_document_parser.py` | 8+ | txt 成功 / pdf 成功（mock pypdf）/ docx 成功（mock python-docx）/ xlsx 成功（mock openpyxl）/ pptx 成功（mock python-pptx）/ 多文件合并 / 截断 8000 / 全失败抛错 |

### 10.2 operator 集成测试（test_operator_seeding_writer.py，35+ 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 鉴权 | 4 | 无 token / operator OK / admin OK / invalid |
| personas | 3 | 空列表 / 有数据 / 含 creator_name |
| references | 5 | 列表空 / 列表有数据 / 新增 / 删除 / 抖音导入（mock adapter）|
| products | 8 | 列表 / 新增 / 更新 / 软删 / 公司共享（A 创 B 可见）/ parse-document（mock AI）/ 重复名容许 / 鉴权 |
| fetch-video | 3 | 成功 / 空 URL / tikhub 错误 |
| transcribe | 4 | submit 成功（mock 下载+OSS+ASR）/ poll processing / poll done / poll 错误 |
| analyze-structure | 3 | 成功流式 / 空 transcript / AI 失败 |
| ai-recommend | 3 | 成功流式 / 空数据 / AI 失败 |
| chat | 5 | writing 成功 / iteration 成功 / product 不存在 / 无效 scene / 空 messages |
| save-output | 3 | 成功+账号绑定 / 空 content / 账号隔离 |
| export-word | 2 | 成功 / 空 content |
| outputs | 2 | 分页 / 账号隔离 |

### 10.3 admin 集成测试（test_admin_seeding_writer.py，9 用例）

| 分类 | 用例数 | 关键点 |
|------|--------|--------|
| 鉴权 | 4 | admin OK / operator forbidden / invalid / unauthenticated |
| GET configs | 1 | 返回种子（6 Prompt + 2 模型字段）|
| PUT configs | 4 | 更新 6 Prompt / 更新 model IDs / 不存在 404 / 写 OperationLog |

---

## 十一、关键约定

- **3 张新表 + 1 migration**：configs/products/references 一次性建，033 文件
- **6 Prompt 模板化**：DB 存 6 列，后端 `render_prompt()` 渲染（参照 persona-writer 4 Prompt 模式）
- **14 占位符**：单次正则一次性替换（防止二次替换 bug）
- **双模型**：light（claude-haiku-4-5，结构拆解/AI 推荐）+ heavy（claude-opus-4-6，写作/迭代/卖点讨论）
- **ASR 走 submit + poll 分离**：避免长连接超时；前端 60 次×5s 轮询
- **抖音链接导入素材同步阻塞**：低频管理员操作，不需要轮询 UX
- **文档解析 multipart**：例外不走 request.ts 标准 JSON 包装（前端用裸 fetch + FormData）
- **流式例外**：extract-selling-points / analyze-structure / ai-recommend / chat 返回 text/plain 裸文本流
- **export-word 例外**：StreamingResponse（不包信封）
- **products 公司共享 + references 达人维度共享**：不按 created_by 隔离查询，仅审计
- **outputs 账号隔离**：WHERE created_by=current_user.id（同 persona-writer）
- **adapter 复用**：tikhub / oss / asr / yunwu 4 个 adapter 已接通，不新增
- **OperationLog**：references 3 + products 4 + parse-document 1 + fetch-video 1 + transcribe-submit 1 + save-output 1 + PUT configs 1 + chat(create_job=true) 1 共 13 个写入点

---

## 十二、种子 Prompt 来源

| Prompt | 旧版位置 | 改造说明 |
|--------|---------|---------|
| sp_system_prompt | `page.tsx.bak` 第 220-239 行（spSystemPrompt）| `${var}` 无变量；保持原文 |
| parse_product_prompt | `parse-product/route.ts` 第 73-94 行 | 同上 |
| structure_analysis_prompt | `page.tsx.bak` handleAnalyzeStructure 第 476-488 行 | `${transcript}` → `{{transcript}}` |
| ai_recommend_prompt | `page.tsx.bak` handleAiRecommend 第 513-549 行 | `${selectedPersona.soul}` → `{{soul}}`；`${product.name}` → `{{product_name}}` 等 |
| writing_prompt | `page.tsx.bak` handleWrite 第 565-618 行 | 全部 `${var}` → `{{var}}` |
| iteration_prompt | `page.tsx.bak` handleSendChat 第 667-690 行 | 同 writing 改造 |

---

## 十三、不在本次后端范围

- 前端页面（前端任务文档）
- tool_transcribe 改造（独立任务）
- 产品库 Excel 批量导入（独立任务）
- 素材库分类筛选 / 全文搜索（按需迭代）
- 医美锚定独立功能（仅字段存储）

---

## 十四、DoD

- ✅ Migration 033 执行成功，3 张表 + 6 种子 Prompt + workspace_tools online
- ✅ ORM 3 个模型 + __init__ 注册
- ✅ prompt + document_parser service 单测全绿
- ✅ operator 20 接口 + admin 2 接口全部通过鉴权 + 集测
- ✅ convention_guard 6 红线全过
- ✅ 全量 pytest 回归（不引入新 fail）
- ✅ Base_API §23 + Base_Database §27 同步
- ✅ backend/docs/README.md 同步（routers 清单 + migrations 清单）
