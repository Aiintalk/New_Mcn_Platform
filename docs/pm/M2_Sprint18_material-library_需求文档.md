# M2 Sprint 18 — 素材库（material-library）迁移需求文档

> **版本**：v1
> **作者**：MCN_PM_Agent
> **日期**：2026-06-25
> **迁移源**：旧架构 `Ai_Toolbox/material-library-web/`（Next.js 14 + 文件系统存储）
> **参照样板**：persona-positioning（人格定位）、seeding-writer（种草仿写 ConfigTab 模式）

---

## 一、定位

独立工具，新架构的**红人素材中枢**。运营和管理员在此集中管理每个红人的：
- **人格档案**（soul.md）— 富文本人设文档
- **内容规划**（content-plan.md）— 内容策略文档
- **参考素材**（6 种类型文案）— 手动录入的参考脚本

与 persona-positioning 的 persona_reports **保持独立**，不合并。

---

## 二、迁移红线对照

| 红线 | 本功能如何满足 |
|------|--------------|
| #1 运营端入口在「创作中心」 | 创作中心新增「素材库」工具卡片 |
| #2 产出在「产出中心」显示 | N/A — 素材库是数据管理工具，不产生"产出"（非 AI 创作工具） |
| #3 公共服务用统一 adapter | AI 调用走 yunwu adapter（soul.md 初稿生成） |
| #4 Prompt + 模型在管理端可配 | 管理端「工具配置」→「素材库配置」Tab，含 AI 模型 + Prompt |
| #5 纳入管理端「功能配置」 | workspace_tools 注册 tool_code=`material-library`，dev→online |
| #6 调用第三方写日志 | AI 调用通过 yunwu adapter 自动写 ai_call_logs + external_service_logs |
| #7 拿不准参照已迁功能 | 参照 persona-positioning（红人列表 + 富文本）、seeding-writer（ConfigTab） |

---

## 三、核心功能（6 项）

### 3.1 红人列表

- 数据源：复用 `kols` 表（不新增红人实体）
- 展示：红人名 / 抖音号 / soul.md 有无 / content-plan.md 有无 / 素材总数 / 入驻问卷状态
- 搜索：按红人名搜索
- 排序：按更新时间倒序

### 3.2 人格档案编辑（soul.md）

- 每个红人一份 soul.md（富文本 Markdown），存入 **kols.persona** 字段（复用已有字段，不新建表）
- 支持：查看 / 编辑 / 保存
- 编辑器：Ant Design TextArea（多行文本，与 soul.md 原始 Markdown 对应）
- soul.md 非必填，空则显示"暂无人格档案"

### 3.3 内容规划编辑（content-plan.md）

- 每个红人一份 content-plan.md，存入 **kols.content_plan** 字段（复用已有字段）
- 交互同 3.2

### 3.4 参考素材管理

**6 种类型**（保持旧架构分类不变）：

| 分组 | 类型 | 说明 |
|------|------|------|
| 人设仿写素材 | 红人爆款文案 | 达人数据好的视频文案 |
| | 红人喜欢的内容 | 达人觉得好、想参考的内容 |
| | 风格参考 | 达人语气、表达方式参考 |
| 千川仿写素材 | 千川爆款文案 | 跑量好的千川素材脚本 |
| | 千川喜欢的内容 | 觉得好、想参考的千川内容 |
| | 千川风格参考 | 千川素材语气、表达方式参考 |

**操作**：
- 添加：选类型 + 填标题（必填）+ 填点赞数（选填）+ 粘贴正文（必填）→ 保存
- 查看：按类型分组展示，支持类型筛选
- 删除：单条删除（软删除）
- 字段：title / likes(INT) / source(默认"抖音") / type(6选1) / content(TEXT) / created_at

### 3.5 KOL intake 联动

**只读展示 + AI 生成初稿**：

- **关联方式**：通过红人名（kols.name）匹配 kol-intake 的 kol_name（字符串弱关联）
- **只读展示**：展示该红人的入驻问卷回答（24 个字段）+ AI 分析报告
- **AI 生成 soul.md 初稿**（新功能，旧架构无）：
  - 用户点击"从入驻问卷生成人格档案"按钮
  - 后端取该红人的 intake 数据（answers + report），用**可配置 Prompt**（管理端配）+ **可配置 AI 模型**调用 yunwu adapter
  - AI 生成 soul.md 初稿，返回前端
  - 用户在前端 TextArea 中查看/编辑/保存（不自动覆盖已有 soul.md）
  - 若已有 soul.md，提示"将覆盖现有内容"，用户确认后填充到编辑器（不直接保存，需手动点保存）

### 3.6 旧数据迁移

- 旧数据量：2 个红人（孙静、陶然），各 1 份 soul.md + 1 份 content-plan.md，0 条素材
- 迁移方式：后端脚本 / SQL 导入，通过红人名匹配 kols 表
- 红人名匹配不上的：在 kols 表创建新红人记录后导入
- 迁移文件：`backend/scripts/migrate_material_library.py`（从旧 `data/personas/` 读取 → 写入 kols.persona / kols.content_plan）

---

## 四、数据库设计

### 4.1 复用 kols 表已有字段（不新建 profile 表）

| soul.md 对应 | content-plan.md 对应 | 说明 |
|-------------|---------------------|------|
| `kols.persona` (Text) | `kols.content_plan` (Text) | 已有字段，直接存 soul.md / content-plan.md 全文 |

> **不新建 kol_profiles 表**——kols 表已预留 persona / content_plan 字段，直接复用，零迁移成本。

### 4.2 新增表

#### kol_references（红人参考素材）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | 主键 |
| kol_id | BIGINT NOT NULL REFERENCES kols(id) ON DELETE CASCADE | 关联红人 |
| title | VARCHAR(500) NOT NULL | 标题 |
| likes | INT | 点赞数 |
| source | VARCHAR(100) DEFAULT '抖音' | 来源 |
| type | VARCHAR(50) NOT NULL | 类型（6 种之一） |
| content | TEXT NOT NULL | 正文 |
| created_at | TIMESTAMPTZ DEFAULT NOW() | |
| deleted_at | TIMESTAMPTZ | 软删除 |

> 索引：kol_id + type + deleted_at（按类型筛选）；kol_id + created_at DESC（按时间排序）

#### material_library_configs（管理端配置）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL PK | 主键 |
| config_key | VARCHAR(100) NOT NULL UNIQUE | 配置键 |
| ai_model_id | BIGINT REFERENCES ai_models(id) | AI 模型 |
| system_prompt | TEXT | 系统提示词 |
| is_active | BOOLEAN DEFAULT TRUE | 是否启用 |
| updated_at | TIMESTAMPTZ DEFAULT NOW() | |

> config_key 预置：`soul_generator`（soul.md 初稿生成 Prompt + 模型）

### 4.3 Migration 文件

`backend/migrations/034_material_library.sql`：建上述 2 张表 + 索引 + 预置 soul_generator 默认 Prompt

### 4.4 workspace_tools 注册

`backend/migrations/034_material_library.sql` 追加：
```sql
INSERT INTO workspace_tools (tool_code, tool_name, category, status, sort_order, description)
VALUES ('material-library', '素材库', '内容工作台', 'dev', 18, '红人素材中枢：人格档案+内容规划+参考素材管理')
ON CONFLICT (tool_code) DO UPDATE SET tool_name=EXCLUDED.tool_name;
```

---

## 五、API 设计

### 5.1 运营端（/api/operator/material-library）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/kols` | 红人列表（含 profile 概况 + 素材数 + intake 状态） |
| GET | `/kols/{kol_id}` | 红人详情（profile + references 按类型分组） |
| PUT | `/kols/{kol_id}/profile` | 更新 kols.persona（soul.md）/ kols.content_plan（content-plan.md） |
| POST | `/kols/{kol_id}/references` | 添加素材 |
| DELETE | `/kols/{kol_id}/references/{ref_id}` | 删除素材（软删除） |
| GET | `/kols/{kol_id}/intake` | 获取关联的入驻问卷数据（只读） |
| POST | `/kols/{kol_id}/generate-soul` | AI 生成 soul.md 初稿（流式或非流式） |

### 5.2 管理端（/api/admin/material-library）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/configs` | 获取配置（soul_generator Prompt + 模型） |
| PUT | `/configs` | 更新配置 |

### 5.3 鉴权

- 运营端：`get_current_user`（登录即可访问）
- 管理端：`require_admin`
- 所有写操作（PUT/POST/DELETE）必须写 OperationLog

### 5.4 AI 生成 soul.md 初稿（generate-soul 端点）

**流程**：
1. 取 kol_id 对应的 kols.name
2. 用 kols.name 匹配 kol_intake_submissions / kol_intake_operator_sessions 中的 kol_name
3. 取 intake 的 answers + report
4. 从 material_library_configs 取 soul_generator 的 system_prompt + ai_model_id
5. 调用 yunwu adapter（非流式，因为 soul.md 是完整文档不需要流式体验）
6. 返回 AI 生成的 soul.md 文本
7. **不自动保存**——返回给前端，用户编辑后手动保存

**异常处理**：
- 红人无 intake 数据 → 返回 error_response（提示"该红人暂无入驻问卷数据"）
- AI 调用失败 → 返回 error_response（透传错误信息）
- 未配置 Prompt/模型 → 返回 error_response（提示"请联系管理员配置素材库 AI 设置"）

---

## 六、前端设计

### 6.1 运营端页面（MaterialLibraryPage.tsx）

**布局**：左右分栏（参照 PersonaPage）

- **左侧**：红人列表（搜索框 + 列表），每行显示：红人名 / soul.md●(有/无) / 素材数 / intake●(有/无)
- **右侧**：选中红人后，Tab 切换 4 个面板：

| Tab | 内容 |
|-----|------|
| 人格档案 | soul.md 编辑器（TextArea）+ "从入驻问卷生成"按钮 + 保存按钮 |
| 内容规划 | content-plan.md 编辑器（TextArea）+ 保存按钮 |
| 参考素材 | 6 类型分组展示 + 添加素材表单（Modal）+ 删除按钮 |
| 入驻信息 | 只读展示 intake 问卷数据 + AI 报告（如有关联） |

### 6.2 管理端配置页（MaterialLibraryConfigTab.tsx）

参照 SeedingWriterConfigTab 模式：
- AI 模型 Select（从 ai_models 读取）
- soul_generator 系统提示词 TextArea
- 启用/停用开关
- 保存按钮

注册到 WorkspaceConfigPage.tsx 的 Tabs 中。

### 6.3 路由

- 运营端：`/operator/material-library` → MaterialLibraryPage
- 入口：创作中心 WorkspacePage 工具卡片（tool_code=`material-library`）

---

## 七、不做清单

- ❌ 视频转录流水线（TikHub→OSS→ASR）— 已被 subtitle-extractor 取代
- ❌ AI 通用 chat — 已被各 writer 工具各自实现
- ❌ 不与 persona-positioning 的 persona_reports 合并
- ❌ 不自动采集素材（纯手动录入，与旧架构一致）
- ❌ 不新增顶级侧边栏菜单（入口在创作中心）

---

## 八、验收标准

1. ✅ 运营端创作中心可见「素材库」工具卡片，点击进入红人列表
2. ✅ 红人列表从 kols 表读取，展示 profile 概况 + 素材数 + intake 状态
3. ✅ 可编辑/保存 soul.md 和 content-plan.md
4. ✅ 可添加/查看/删除 6 种类型的参考素材
5. ✅ 入驻信息 Tab 展示关联的 kol-intake 数据（如有关联）
6. ✅ "从入驻问卷生成"按钮能调 AI 生成 soul.md 初稿（需管理员先配置 Prompt）
7. ✅ 管理端「工具配置」→「素材库配置」可配 AI 模型 + Prompt
8. ✅ 旧数据（2 个红人）成功导入
9. ✅ 所有 API 返回标准信封，写操作有 OperationLog
10. ✅ AI 调用产生日志（ai_call_logs + external_service_logs）
11. ✅ 后端测试通过（pytest），前端测试通过（vitest）
12. ✅ 契约文档（Base_API + Base_Database）同步更新
13. ✅ 前后端 README 同步更新

---

## 九、技术要点

### 9.1 与 kols 表的关系
- **直接读写**：素材库从 kols 表读取红人列表，soul.md / content-plan.md 直接存入 kols.persona / kols.content_plan 字段
- 红人的基本信息（姓名/抖音号/粉丝数等）仍在管理端 KolsPage 管理
- 素材库只读写 kols 的 persona / content_plan 两个字段 + 管理 kol_references 素材

### 9.2 与 kol-intake 的关联
- kol-intake 使用 kol_name（字符串）关联，无 FK
- 关联方式：`kols.name LIKE kol_intake_links.kol_name`（模糊匹配，因为名字可能不完全一致）
- 如有多条匹配，取最新一条

### 9.3 soul.md 格式
- 纯 Markdown 文本，前端用 TextArea 编辑（不做 Markdown 渲染，保持原始文本编辑）
- 长度：旧架构 soul.md 约 6000-16000 字符，TEXT 字段足够

### 9.4 ConfigTab Prompt 设计（soul_generator）
- 输入：红人的 intake 问卷数据（answers JSON + AI report 文本）
- 输出：soul.md 格式的人设文档
- Prompt 中需包含 soul.md 的结构模板（一句话定位、基本信息表格、人设内核、说话风格等）
- 默认 Prompt 在 migration 中预置，管理员可修改

---

## 十、实施计划（TDD）

| 步骤 | 内容 | 预估 |
|------|------|------|
| Step 1 | Migration 030 + ORM 模型 + 注册 | 0.5 天 |
| Step 2 | 后端 API（7 运营端 + 2 管理端）+ 单测 + 集成测试 | 1.5 天 |
| Step 3 | 前端 API 层 + MaterialLibraryPage + ConfigTab + 测试 | 1.5 天 |
| Step 4 | 旧数据迁移脚本 + 执行 | 0.5 天 |
| Step 5 | 文档更新（契约 + README + PM 记忆） | 0.5 天 |
| Step 6 | 端到端联调 + 全量回归 | 0.5 天 |
| **合计** | | **~5 天** |

---

## 十一、依赖

- yunwu adapter（AI 调用）— 已就绪
- kols 表 — 已存在（M1）
- kol-intake 数据 — 已存在（M2 Sprint 1）
- ai_models 表 — 已存在（管理端 AI 模型管理）
