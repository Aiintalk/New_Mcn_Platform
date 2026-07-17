# M2 Sprint 23 — 后端任务：红人工作台旧版功能还原 v1（PR #28 补归档）

> **归档性质说明（2026-07-17）：** 本任务是 PR #28 `feature/kol-core-workflow`（merge `ba376ce9`，2026-07-17 合入 main）的**回顾性任务单归档**。开发期实际未单独建任务单，PR 合并后由 PM 审计发现缺口并补齐，便于后续追溯。
> **开发期时间：** 2026-07-14（需求 v1 落档）至 2026-07-17（合并 main）
> **需求来源：** `docs/pm/M2_红人工作台旧版功能还原_需求文档_v1.md`
> **契约来源：** `backend/docs/base/MCN_M2_Base_API.md` §30 · `MCN_M2_Base_Database.md`（migration 049-052 + 完整视频数据边界）
> **后端约定：** `backend/docs/后端开发约定.md`（必读，动手前通读）

---

## 一、任务范围

### 模块覆盖

| # | 模块 | 后端改动 |
|---|---|---|
| 1 | 人物档案统一读取 | 新建 `services/kol_context.py`：聚合 5 分区 + 独家经历等完整字段，供千川/价值观/直播/复盘复用 |
| 2 | 产品库 + 单一当前商品 | migration 049 加 `uq_kol_active_products_kol` 唯一约束；`operator_qianchuan_products.py` 切换商品时替换旧关联 |
| 3 | 千川仿写闭环 | `operator_qianchuan_writer.py` 还原初稿 → 自动预审 → 自动重写 → 最好版本；商品卖点真实进入 prompt（修复 productText 未传 bug） |
| 4 | 价值观四步流程 | `operator_values_writer.py` 重构为旧版四步（情绪方向推导 + 结构化初稿 + 多轮迭代 + 双字组合相似度） |
| 5 | 直播脚本上下文 | `operator_livestream_writer.py` 接通当前商品 + 完整人物上下文 + 七模块输出 |
| 6 | 素材库媒体能力 | migration 050 加 `material_library` 媒体字段；`operator_material_library.py` 文档解析 + OSS 私有视频上传/替换/软删除 |
| 7 | 复盘多脚本逐份解析 | `operator_retrospective.py` 修复多文件解析（不合并到第一条） |
| 8 | 千川成片预审完整视频 | migration 051 加 `full_video` 配置键 + migration 052 启用工作台页签；`operator_qianchuan_preview.py` 新增完整视频路径；新建 `adapters/gemini_video.py` |

### 实际改动文件清单

**Migration（4 个新文件）：**

| 文件 | 用途 |
|---|---|
| `migrations/049_kol_active_products_single_current_product.sql` | 加 `uq_kol_active_products_kol` 唯一约束（每红人最多一条有效关联） |
| `migrations/050_material_library_media.sql` | `material_library` 加 `media_url` / `media_oss_key` / `media_duration_ms` 等字段 |
| `migrations/051_qianchuan_full_video_preview_config.sql` | 初始化 `qianchuan_preview_configs` 独立 `full_video` 配置键 |
| `migrations/052_enable_qianchuan_full_video_workspace_tab.sql` | `kol_workspace_configs.enabled_tabs` 默认值加 `film-review` |

**新增 / 改造 Adapter（2 个）：**

| 文件 | 用途 |
|---|---|
| `app/adapters/gemini_video.py` | **新建** Gemini 完整视频适配器：Files API 上传 + 轮询 ACTIVE + 流式分析 + 临时文件清理 |
| `app/adapters/oss.py` | 加私有桶上传 / 15 分钟短时签名读取 / 替换 / 删除；finally 块写 `oss_call_logs` |

**新增 / 改造 Model（3 个）：**

| 文件 | 改动 |
|---|---|
| `app/models/kol_active_product.py` | 单一当前商品约束（配合 migration 049） |
| `app/models/kol_workspace_config.py` | 加 `film-review` WorkspaceTabCode |
| `app/models/material_library.py` | 加媒体字段（配合 migration 050） |

**新增 / 改造 Service（3 个）：**

| 文件 | 用途 |
|---|---|
| `app/services/kol_context.py` | **新建** 人物上下文聚合：persona / content_plan / background / experience / relationships / unique_story / extra_notes |
| `app/services/document_parser.py` | 加 PDF / DOCX / XLSX / PPTX / TXT 多格式解析 |
| `app/services/qianchuan_writer_prompt.py` | 商品卖点 + 主推机制 + "只有我有" 真实进入 AI 输入 |

**改造 Router（9 个）：**

| 文件 | 改动 |
|---|---|
| `app/routers/operator_workspace.py` | dashboard "在售商品" → "当前商品"（单选） |
| `app/routers/operator_qianchuan_products.py` | 单一当前商品切换逻辑 |
| `app/routers/operator_qianchuan_writer.py` | 自动预审闭环 + 商品输入修复 |
| `app/routers/operator_qianchuan_preview.py` | 新增完整视频路径（`POST /api/tools/qianchuan-preview/analyze-full-video`）；改用直接 import `AsyncSessionLocal`（PM 接手修复红线 #7） |
| `app/routers/operator_values_writer.py` | 重构为旧版四步流程；**PM 接手修复：3 处 POST 补 OperationLog**（derive_directions / generate_value_script / iterate_structured_value_script） |
| `app/routers/operator_livestream_writer.py` | 接通当前商品 + 完整人物上下文 |
| `app/routers/operator_material_library.py` | 文档解析 + OSS 私有视频 CRUD + 红人路径隔离 |
| `app/routers/operator_retrospective.py` | 多脚本逐份解析修复 + 失败不伪完成 |
| `app/routers/operator_script_review.py` | 兼容千川直销 / 价值观双模式（既有，配合价值观重构） |

**测试（13 个测试文件）：**

- `backend/tests/conftest.py`：补 `app.routers.operator_qianchuan_preview.AsyncSessionLocal` 到 `_SESSION_LOCAL_PATCH_TARGETS`
- `tests/integration/routers/`：test_auth / test_livestream_writer / test_operator_material_library / test_operator_qianchuan_video_preview / test_operator_qianchuan_writer / test_operator_retrospective / test_operator_script_review / test_operator_values_writer / test_operator_workspace（9 个）
- `tests/unit/adapters/test_gemini_video.py`
- `tests/unit/models/test_kol_workspace_config.py`
- `tests/unit/services/test_document_parser.py` / `test_oss_adapter.py` / `test_qianchuan_writer_prompt.py`

**依赖更新：**

- `backend/requirements.txt`：加 Gemini / OSS / 文档解析相关依赖

---

## 二、Migration 文件

### 049_kol_active_products_single_current_product.sql

加唯一约束，保证每个红人在同一时间最多有一个当前商品。**生产环境执行前必须先排查 `kol_active_products` 是否已存在重复 `kol_id`**（项目无 schema_migrations 表，迁移手动 psql 跑，详见 `db_migration_gap.md`）。

### 050_material_library_media.sql

`material_library` 加媒体字段：`media_url` / `media_oss_key` / `media_duration_ms` / `media_uploaded_at` 等。配合 OSS 私有桶短时签名读取。

### 051_qianchuan_full_video_preview_config.sql

`qianchuan_preview_configs` 初始化独立 `full_video` 配置键，与既有 `default` 配置键分离（`default` 仍只用于文案预审）。完整视频绑定的 `ai_models` 必须是 `provider='gemini'` + `status='active'` 的模型。

### 052_enable_qianchuan_full_video_workspace_tab.sql

`kol_workspace_configs.enabled_tabs` 默认值加 `film-review`。**注意：迁移只补充系统默认页签，不改变历史红人、商品、素材或产出数据**。

---

## 三、不做（本 Sprint 严禁越界）

- 不开发、不接入 TikTok 工具
- 不接入 `dysync.net` / `douyin-live-platform` 自动采集
- 不接入云视频
- 不迁移旧版慧敏工作台的历史人物档案、商品、素材和复盘数据
- 不删除既有种草仿写 / 人设仿写 / 直播复盘 / 千川脚本预审 / 千川剪辑预览（关键帧）等额外模块或独立路由
- 不修改 `kols.status` DB 列（已 deprecated，代码不再读写，未来通过 migration 删除）
- 不在代码或环境文件中写死 Gemini 凭证、模型或提示词

---

## 四、关键架构约束

### 4.1 完整视频成片预审（最容易踩坑）

- 前端不得直接调用 Gemini
- Gemini 凭证、模型和提示词必须进入管理端统一配置
- 后端通过平台适配层 `adapters/gemini_video.py` 调用，并写 `ai_call_logs`
- 大文件不得长期保存在应用服务器本地磁盘（用临时目录 + OSS + Gemini Files API，处理完成或失败后按策略清理）
- **不允许静默退化为关键帧模式**：完整视频能力不可用时，必须明确提示配置或服务问题
- 现有"千川剪辑预审"关键帧工具（`tool_qianchuan_edit_review.py`）保留，不在本轮删除

### 4.2 素材库 OSS 安全

- 视频通过平台 OSS adapter 上传，不存本地永久路径
- 播放地址使用后端鉴权或 15 分钟短时签名地址
- 删除使用软删除或业务删除策略，同时按对象存储规范处理视频对象；禁止直接物理删除数据库记录
- 对象存储上传、签名读取和删除操作均有 `oss_call_logs` 服务日志

### 4.3 七红线合规（PM 接手修复后）

| # | 红线 | 状态 | 备注 |
|---|---|---|---|
| 1 | 非流式接口标准信封 | ✅ | 流式和文件下载作为例外 |
| 2 | POST/PUT/PATCH/DELETE 写 OperationLog | ✅ | **PM 修复**：values_writer 3 处 POST 补 OperationLog |
| 3 | 前端 JSON 走 request.ts | ✅ | 前端 `api/filmReview.ts` 等遵守 |
| 4 | 契约文档同步 | ✅ | `Base_API` §30 + `Base_Database` migration 051 + 数据边界说明 |
| 5 | 功能完成后更新 README | ✅ | 根 README + backend/docs/README + **frontend/docs/README（本 PR 补）** |
| 6 | AiCallLog 由 adapter 层写 | ✅ | `gemini_video.py` / `oss.py` 在 finally 块写日志 |
| 7 | AsyncSessionLocal 注册到 conftest | ✅ | **PM 修复**：`operator_qianchuan_preview.py` 改直接 import + 加入 patch 列表 |

---

## 五、验收结果

**功能验收：通过**（详见 `docs/pm/M2_红人工作台旧版功能还原_最终联合验收报告.md`）

**测试通过情况（合并 main 时）：**

- 八模块后端定向回归：227 通过（14 个 router/service 测试文件）
- qianchuan-preview 完整视频：30 通过（含 Gemini adapter + 失败恢复 + 清理策略）
- 前端 `tsc -b`：PR #30 hotfix 后通过
- CI（GitHub Actions）：1300+ passed

**真实验证证据（联合验收期）：**

- 测试达人（编号 2）使用 `original_交个朋友-weiyimei.mp4` + `edited_交个朋友-weiyimei2.mp4` 完成 Gemini 完整视频分析：任务 9 成功，耗时 98,666 毫秒，3,051 字报告已保存并导出 Word
- 任务载荷为 `full_video`，两条视频均以完整视频对象传入，无关键帧降级
- OSS 私有桶：真实上传 / 15 分钟短时读取 / 替换 / 删除均通过，临时素材记录和远端对象已清理
- Gemini 统一凭证池 + `Gemini 2.5 Flash（完整视频）` 模型 + `full_video` 绑定已在 `mcn_m1` 配置完成

**已知遗留（非代码阻断）：**

- migration 049-052 需在生产 psql 手动执行（项目无 schema_migrations 表）
- migration 049 唯一约束要求 `kol_active_products` 无重复 `kol_id`，**生产环境跑前需先排查**
- 5 份真实复盘源文件待补齐（联合验收前置条件）

---

## 六、契约影响

### 接口契约（`backend/docs/base/MCN_M2_Base_API.md`）

新增 §30「qianchuan-preview 完整视频成片预审」，含：
- 路由前缀 `/api/tools/qianchuan-preview`
- `POST /analyze-full-video`（multipart/form-data：`kol_id` + `original` + `edited`）
- 服务端限制：仅 `.mp4` / `.mov` + 500MB / 文件
- 完整视频固定读取 `full_video` 配置键，绑定模型必须 `provider='gemini'` + `status='active'`
- 失败明确报错，绝不退化为关键帧
- 任务载荷只记录临时对象键和文件元数据；处理结束后清理对象存储和 Gemini 临时文件

### 数据库契约（`backend/docs/base/MCN_M2_Base_Database.md`）

- migration 049-052 已登记
- 完整视频预审**不新增业务表**：复用 `qianchuan_preview_configs` / `ai_models` / `credentials` / `task_jobs` / `outputs` / `external_service_logs` / `ai_call_logs` / `oss_call_logs`

---

## 七、参考

- 开发分支：`feature/kol-core-workflow`（已合并）
- 需求 v1：`docs/pm/M2_红人工作台旧版功能还原_需求文档_v1.md`
- 开发验收清单：`docs/pm/M2_红人工作台旧版功能还原_开发验收清单.md`
- 最终联合验收报告：`docs/pm/M2_红人工作台旧版功能还原_最终联合验收报告.md`
- 测试报告：`backend/docs/tests/M2_红人工作台旧版功能还原_测试报告.md`
- PM 接手修复记录：`docs/pm/PM_记忆与状态_M2.md`（PR #28+29+30 同日合并段）
