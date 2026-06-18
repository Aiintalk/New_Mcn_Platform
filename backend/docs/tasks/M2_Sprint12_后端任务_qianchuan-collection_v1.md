# M2 Sprint 12 — 后端任务：千川爆文合集（qianchuan-collection）v1

> 状态：待开发
> 对应需求文档：`docs/pm/M2_Sprint12_qianchuan-collection_需求文档.md`

---

## 一、任务清单

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| B1 | 数据库迁移（2 张表 + 种子数据 + workspace_tools 注册） | `backend/migrations/025_qianchuan_collection.sql` | ⬜ 待做 |
| B2 | SQLAlchemy 模型 | `backend/app/models/qianchuan_collection.py` | ⬜ 待做 |
| B3 | operator 路由（7 个接口） | `backend/app/routers/operator_qianchuan_collection.py` | ⬜ 待做 |
| B4 | main.py 注册 | `backend/app/main.py` | ⬜ 待做 |
| B5 | conftest.py 注册（如用到 AsyncSessionLocal） | `backend/tests/conftest.py` | ⬜ 待做 |
| B6 | 单元测试 | `backend/tests/unit/routers/test_qianchuan_collection_unit.py` | ⬜ 待做 |
| B7 | 集成测试 | `backend/tests/integration/routers/test_qianchuan_collection.py` | ⬜ 待做 |

---

## 二、数据库设计

### 迁移文件：`025_qianchuan_collection.sql`

#### 表 1：`qianchuan_collection_personas`（达人分组表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | SERIAL PRIMARY KEY | 主键 |
| `name` | VARCHAR(100) NOT NULL UNIQUE | 达人名称（唯一） |
| `is_deleted` | BOOLEAN NOT NULL DEFAULT FALSE | 软删除标志 |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 更新时间（触发器自动） |

#### 表 2：`qianchuan_collection_scripts`（脚本表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | SERIAL PRIMARY KEY | 主键 |
| `pool` | VARCHAR(20) NOT NULL DEFAULT 'global' | 脚本池（'global' / 'persona'） |
| `persona_name` | VARCHAR(100) | 达人名称（pool=persona 时有值） |
| `title` | VARCHAR(200) NOT NULL | 脚本标题 |
| `content` | TEXT NOT NULL | 脚本正文 |
| `likes` | INTEGER | 点赞数（选填） |
| `source` | VARCHAR(100) | 来源平台（选填） |
| `source_account` | VARCHAR(100) | 来源账号（选填） |
| `script_date` | DATE | 脚本日期（选填，默认当天） |
| `is_deleted` | BOOLEAN NOT NULL DEFAULT FALSE | 软删除标志 |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | 更新时间（触发器自动） |

**索引**：
- `(pool, is_deleted)` — 列表查询主路径
- `(persona_name, is_deleted)` — 按达人查脚本

#### workspace_tools 注册

```sql
INSERT INTO workspace_tools (tool_code, tool_name, category, description, status, tags, sort_order)
VALUES (
    'qianchuan-collection',
    '千川爆文合集',
    '千川',
    '收集管理全网高跑量千川脚本，按全网爆款和达人爆款两个维度分池管理',
    'online',
    '["脚本","千川","素材库"]'::jsonb,
    (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM workspace_tools WHERE category = '千川')
)
ON CONFLICT (tool_code) DO NOTHING;
```

#### 种子数据

将旧工具 `data/global/scripts/` 下约 40 条 .md 文件解析后，作为 INSERT 语句写入 `qianchuan_collection_scripts`（pool='global'）。  
文件名格式：`{timestamp}-{title}.md`，frontmatter 含 title/date/likes/source/source_account。

---

## 三、接口说明

### 鉴权守卫（统一）

所有接口要求：`role in ('operator', 'admin')` 且 `password_changed_at IS NOT NULL`。

---

### GET `/api/tools/qianchuan-collection/personas`

获取达人列表（不含已软删除的）。

**响应**（标准信封）：
```json
{
  "data": {
    "personas": [
      { "name": "达人A", "script_count": 5 }
    ]
  }
}
```

---

### POST `/api/tools/qianchuan-collection/personas`

新建达人分组。

**请求体**：
```json
{ "name": "达人A" }
```

**逻辑**：
- 名称不能为空，不超过 100 字
- 名称不能与已存在（is_deleted=false）的达人重名 → 409
- 写 OperationLog（action=`collection_persona_create`）

**响应**：`{ "data": { "name": "达人A" } }`

---

### DELETE `/api/tools/qianchuan-collection/personas/{persona_name}`

软删除达人（同时软删该达人下所有脚本）。

**逻辑**：
- `UPDATE qianchuan_collection_personas SET is_deleted=true WHERE name=:name`
- `UPDATE qianchuan_collection_scripts SET is_deleted=true WHERE persona_name=:name`
- 写 OperationLog（action=`collection_persona_delete`）

**响应**：`{ "data": { "ok": true } }`

---

### GET `/api/tools/qianchuan-collection/scripts`

获取脚本列表，支持分页和筛选。

**Query 参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `pool` | string | 必填 | `global` 或 `persona` |
| `persona_name` | string | — | pool=persona 时必填 |
| `q` | string | — | 关键词搜索（title + content ILIKE） |
| `page` | int | 1 | 页码 |
| `page_size` | int | 20 | 每页条数（最大 100） |

**响应**（标准信封）：
```json
{
  "data": {
    "scripts": [
      {
        "id": 1,
        "title": "...",
        "content": "...",
        "likes": 50000,
        "source": "抖音",
        "source_account": "某账号",
        "script_date": "2026-06-18",
        "pool": "global",
        "persona_name": null,
        "created_at": "2026-06-18T10:00:00Z"
      }
    ],
    "total": 42,
    "page": 1,
    "page_size": 20
  }
}
```

---

### POST `/api/tools/qianchuan-collection/scripts`

新增脚本。

**请求体**：
```json
{
  "pool": "global",
  "persona_name": null,
  "title": "脚本标题",
  "content": "脚本正文...",
  "likes": 50000,
  "source": "抖音",
  "source_account": "某账号",
  "script_date": "2026-06-18"
}
```

**逻辑**：
- title/content 必填，不能为空
- pool=persona 时 persona_name 必填，且对应达人必须存在（is_deleted=false）
- script_date 未传则默认今天
- 写 OperationLog（action=`collection_script_create`）

**响应**：`{ "data": { "id": 123 } }`

---

### DELETE `/api/tools/qianchuan-collection/scripts/{script_id}`

软删除脚本。

**逻辑**：
- `UPDATE ... SET is_deleted=true WHERE id=:id`
- 记录不存在或已删除 → 404
- 写 OperationLog（action=`collection_script_delete`）

**响应**：`{ "data": { "ok": true } }`

---

### POST `/api/tools/qianchuan-collection/parse-file`

上传文件，解析返回文本。

**请求**：`multipart/form-data`，`file` 字段（.txt / .md / .docx / .pdf）

**逻辑**：复用 `file_parser.py` 中现有解析能力（txt/md 直读，docx 用 python-docx，pdf 用 pdfminer）

**响应**：`{ "data": { "text": "...", "filename": "原文件名" } }`

> 无 OperationLog（只读解析，无数据写入）

---

## 四、无需新增内容

- **无 AI 调用** → 无 yunwu adapter、无 AiCallLog、无 Prompt 常量、无 tools/ 子目录
- **无管理端专属接口** → 无 admin_qianchuan_collection.py
- **无 AsyncSessionLocal** → B5 步骤（conftest 注册）大概率不需要，开发时确认

---

## 五、测试要求

### 单元测试（B6）

覆盖纯逻辑函数（如有）：
- 分页参数校验（page_size 超限截断）
- pool=persona 但 persona_name 为空时的校验

### 集成测试（B7）

覆盖目标：operator 路由覆盖率 ≥ 80%

| 测试用例 | 说明 |
|---------|------|
| GET personas — 正常返回列表 | |
| POST personas — 创建成功 | |
| POST personas — 名称重复 → 409 | |
| POST personas — 名称为空 → 400 | |
| DELETE personas — 成功软删，脚本也随之软删 | |
| GET scripts global — 正常分页 | |
| GET scripts persona — 按达人筛选 | |
| GET scripts — 关键词搜索 | |
| POST scripts global — 创建成功 | |
| POST scripts persona — 达人不存在 → 400 | |
| POST scripts — title 为空 → 400 | |
| DELETE scripts — 成功软删 | |
| DELETE scripts — 不存在 → 404 | |
| POST parse-file — txt 解析成功 | |
| 未登录访问 → 401 | |
| operator 角色访问 → 正常 | |
