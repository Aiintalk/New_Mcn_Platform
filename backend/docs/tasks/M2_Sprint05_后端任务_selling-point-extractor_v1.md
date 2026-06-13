# M2 Sprint 5 · 后端任务 · selling-point-extractor v1

> 状态：✅ 已完成（2026-06-13）
> 需求文档：`docs/pm/M2_Sprint05_selling-point-extractor_需求文档.md`
> 实施计划：`docs/superpowers/plans/2026-06-13-selling-point-extractor-migration.md`

---

## 一、新建 / 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/migrations/015_selling_point_extractor.sql` | 新建 | selling_point_configs 表 + 初始配置 + workspace_tools 注册 |
| `backend/app/models/selling_point.py` | 新建 | SellingPointConfig ORM 模型 |
| `backend/app/routers/admin_selling_point.py` | 新建 | 管理端 GET/PUT configs 接口 |
| `backend/app/routers/operator_selling_point.py` | 新建 | 运营端 5 个接口（chat/parse-file/history CRUD）|
| `backend/app/services/file_parser.py` | 修改 | 追加 `parse_selling_point_file()` + `_parse_pdf_plumber()` + `_parse_pages_selling_point()` |
| `backend/app/models/__init__.py` | 修改 | 注册 SellingPointConfig |
| `backend/app/main.py` | 修改 | 注册两个新 router |
| `backend/tests/unit/services/test_selling_point_file_parser.py` | 新建 | file_parser 单元测试 15 个用例 |
| `backend/tests/integration/routers/test_operator_selling_point.py` | 新建 | 运营端集成测试 20 个用例 |
| `backend/tests/integration/routers/test_admin_selling_point.py` | 新建 | 管理端集成测试 8 个用例 |

---

## 二、接口清单

### 管理端（admin 角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/selling-point/configs` | 配置列表 |
| PUT | `/api/admin/selling-point/configs/{key}` | 更新配置（Prompt / 模型 / 激活状态）|

### 运营端（operator / admin 角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/selling-point-extractor/chat` | AI 流式对话（从 DB 读 Prompt+模型）|
| POST | `/api/tools/selling-point-extractor/parse-file` | 文件解析（支持 .txt/.md/.docx/.pdf/.pages/.doc）|
| GET | `/api/tools/selling-point-extractor/history` | 历史列表 / 单条（全员共享）|
| POST | `/api/tools/selling-point-extractor/history` | 保存历史记录到 outputs 表 |
| DELETE | `/api/tools/selling-point-extractor/history` | 软删除（设 deleted_at）|

---

## 三、数据库

- **新表**：`selling_point_configs`（id / config_key / ai_model_id / system_prompt / is_active / created_at / updated_at）
- **迁移文件**：`migrations/015_selling_point_extractor.sql`（已执行）
- **无新表**（历史记录复用 `outputs` 表，任务记录复用 `task_jobs` 表）

---

## 四、依赖

```
pip install pdfplumber python-snappy
```

新增：`pdfplumber 0.11.9`、`python-snappy 0.7.3`

---

## 五、测试结果

| 测试文件 | 用例数 | 结果 |
|---------|--------|------|
| `test_selling_point_file_parser.py` | 15 | 15/15 ✅ |
| `test_operator_selling_point.py` | 20 | 20/20 ✅ |
| `test_admin_selling_point.py` | 8 | 8/8 ✅ |
| **合计** | **43** | **43/43 ✅** |

**覆盖率（新模块）：**
- `operator_selling_point.py`：**71%**（目标 ≥70%）✅
- `admin_selling_point.py`：**71%**（目标 ≥70%）✅
- `file_parser.py`（含旧测试）：**82%**（目标 ≥80%）✅
