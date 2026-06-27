# M2 Sprint22 后端任务 — 复盘（retrospective）v1

> 编写时间：2026-06-27
> 分支：`feature/kol-workspace`

---

## 一、任务范围

| # | 内容 |
|---|------|
| 1 | Migration 045：`retrospective_sessions` + `retrospective_configs` |
| 2 | ORM 模型：`RetrospectiveSession`、`RetrospectiveConfig` |
| 3 | 管理端 Router：GET/PUT `/api/admin/retrospective/config` |
| 4 | 运营端 Router：CRUD + 文件解析 + 流式分析 + Word 导出 |
| 5 | main.py 注册 + conftest.py 更新 |
| 6 | 集成测试 |

---

## 二、Migration 045

```sql
-- retrospective_configs：复盘 AI 配置（Sprint 22）
CREATE TABLE IF NOT EXISTS retrospective_configs (
    id              BIGSERIAL PRIMARY KEY,
    config_key      VARCHAR(64) NOT NULL UNIQUE,
    system_prompt   TEXT,
    ai_model_id     BIGINT REFERENCES ai_models(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TRIGGER trg_retrospective_configs_updated
    BEFORE UPDATE ON retrospective_configs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
INSERT INTO retrospective_configs (config_key, is_active)
VALUES ('default', TRUE)
ON CONFLICT (config_key) DO NOTHING;

-- retrospective_sessions：复盘记录表（Sprint 22）
CREATE TABLE IF NOT EXISTS retrospective_sessions (
    id               BIGSERIAL PRIMARY KEY,
    kol_id           BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE,
    created_by       BIGINT REFERENCES users(id) ON DELETE SET NULL,
    title            VARCHAR(200) NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'draft',   -- draft / done
    live_data        TEXT,
    material_data    TEXT,
    review_text      TEXT,
    live_script      TEXT,
    material_scripts JSONB,
    result           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_retrospective_sessions_kol_id ON retrospective_sessions(kol_id);
CREATE TRIGGER trg_retrospective_sessions_updated
    BEFORE UPDATE ON retrospective_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## 三、运营端接口（7 个）

路由前缀：`/operator/workspace/{kol_id}/retrospective`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 列表（分页，kol 维度） |
| POST | `/` | 新建/更新（upsert by id） |
| DELETE | `/{id}` | 删除 |
| POST | `/parse-files` | 文件解析（multipart，复用 document_parser） |
| POST stream | `/{id}/analyze` | 流式生成复盘报告 |
| GET | `/{id}/export-word` | 导出 Word（Blob 响应） |

管理端：GET/PUT `/api/admin/retrospective/config`

---

## 四、文件解析

复用 `app/services/document_parser.py` 的 `parse_files_to_text`（已有）。接收 multipart 5 类文件，返回解析后文本。

---

## 五、流式分析逻辑

POST `/{id}/analyze`：
1. 读取 session（kol_id + 5 类材料）
2. 读取 kol 的 `extra_notes`（风格约束）注入 prompt
3. 读取 retrospective_configs default 配置
4. 调 yunwu adapter 流式 chat，SSE 转发
5. 完成后更新 session.result + status='done'

---

## 六、验收口径

1. 全量测试 ≥ 1025 passed
2. GET /api/admin/retrospective/config 返回 default 配置
3. POST /parse-files 返回解析文本
4. POST /{id}/analyze 返回 SSE 流
