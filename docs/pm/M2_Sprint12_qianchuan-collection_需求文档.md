# M2 Sprint 12 — 千川爆文合集（qianchuan-collection）需求文档

> 文档状态：已确认，待开发
> 确认日期：2026-06-18
> 来源：功能迁移自旧工具箱 `Ai_Toolbox_new/qianchuan-collection-web/`

---

## 一、功能概述

**工具名称**：千川爆文合集
**工具代码**：`qianchuan-collection`
**分类**：千川
**路由**：`/workspace/qianchuan-collection`
**状态**：online（迁移时直接上线）

**核心定位**：纯手工脚本收集库，无 AI 调用。供运营人员收集和管理全网高跑量千川脚本，按「全网爆款」和「达人爆款」两个维度分池管理。

---

## 二、功能需求

### 2.1 两个脚本池

| 池类型 | 说明 |
|--------|------|
| **全网爆款**（global） | 全网跑量好的千川脚本，不区分来源达人。预置约 40 条种子数据（从旧工具 `data/global/scripts/` 迁入） |
| **达人爆款**（persona） | 按达人名称分组管理，一个达人对应一批脚本 |

### 2.2 达人管理

- 运营人员可自由创建达人分组，达人名称文字输入，**不绑定 kols 表**（独立维护）
- 支持删除达人（级联删除该达人下所有脚本）
- 达人列表显示每位达人的脚本数量

### 2.3 脚本字段（完整版）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | SERIAL | 是 | 主键 |
| `pool` | ENUM(`global`,`persona`) | 是 | 所属脚本池 |
| `persona_name` | VARCHAR(100) | 否 | 达人名称（pool=persona 时必填） |
| `title` | VARCHAR(200) | 是 | 脚本标题 |
| `content` | TEXT | 是 | 脚本正文 |
| `likes` | INTEGER | 否 | 点赞数 |
| `source` | VARCHAR(100) | 否 | 来源平台（如：抖音、快手） |
| `source_account` | VARCHAR(100) | 否 | 来源账号 |
| `script_date` | DATE | 否 | 脚本日期（默认当天） |
| `created_at` | TIMESTAMPTZ | 是 | 创建时间（自动） |
| `updated_at` | TIMESTAMPTZ | 是 | 更新时间（触发器自动） |

### 2.4 添加脚本

- 手动填写：标题（必填）、内容（必填）、点赞数（选填）、来源平台（选填）、来源账号（选填）
- 上传文件解析：支持 `.docx` / `.pdf` / `.txt` / `.md` → 后端解析返回文本，填充到内容框；文件名作为标题默认值
- 全网爆款模式下直接添加到 global 池；达人爆款模式下需先选择达人

### 2.5 脚本列表与搜索

- 以表格形式展示，显示序号 + 内容开头片段（前 120 字）
- 支持按标题/内容关键词搜索（前端过滤）
- 支持分页（每页 20 条）
- 点击行展开查看全文，展开后可：复制全文到剪贴板、下载 .txt 文件

### 2.6 删除脚本

- 删除前需二次确认
- 软删除（`is_deleted` 标志位），不物理删除（遵循项目九条一票否决项）

### 2.7 管理端

- 在 workspace_tools 表注册该工具（tool_code=`qianchuan-collection`，status=`online`）
- **无专属配置 Tab**（工具无 AI，无需 Prompt/模型配置）
- 管理端「工具配置」页面可查看工具状态开关

---

## 三、与旧工具的差异点

| 维度 | 旧工具（Next.js） | 新平台 |
|------|------------------|-------|
| 数据存储 | 文件系统（.md 文件） | PostgreSQL（`qianchuan_collection_scripts` + `qianchuan_collection_personas` 表） |
| 达人来源 | 文件目录 + 自动从 kol-intake data/ 同步 | 独立手动维护，不与 kols 表联动 |
| 分页 | 无分页（全量加载） | 有分页（每页 20 条） |
| 文件解析 | 前端 mammoth.js + pdf-parse | 后端复用 `parse_qianchuan_review_file` |
| 鉴权 | 无 | JWT（operator/admin） |
| 删除方式 | 物理删除文件 | 软删除（`is_deleted` 标志） |
| 种子数据 | 预置 40 条 .md 文件 | migration 025 seed 数据写入 DB |

---

## 四、接口概览

### 运营端接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/tools/qianchuan-collection/personas` | GET | 获取达人列表（含脚本数量） |
| `/api/tools/qianchuan-collection/personas` | POST | 新建达人 |
| `/api/tools/qianchuan-collection/personas/{persona_name}` | DELETE | 删除达人（级联软删脚本） |
| `/api/tools/qianchuan-collection/scripts` | GET | 获取脚本列表（支持 `pool`/`persona_name`/`q`/`page`/`page_size` 参数） |
| `/api/tools/qianchuan-collection/scripts` | POST | 新增脚本 |
| `/api/tools/qianchuan-collection/scripts/{script_id}` | DELETE | 软删除脚本 |
| `/api/tools/qianchuan-collection/parse-file` | POST | 文件解析，返回文本 |

### 管理端接口

无专属管理端接口（workspace_tools 通过 migration 025 注册，状态由通用管理端接口管理）。

---

## 五、数据库变更

**迁移编号**：`025_qianchuan_collection.sql`

新建两张表：
1. `qianchuan_collection_personas` — 达人分组表
2. `qianchuan_collection_scripts` — 脚本表（含 pool 区分 global/persona）

workspace_tools 注册：

| tool_code | tool_name | category | status | sort_order |
|-----------|-----------|----------|--------|------------|
| `qianchuan-collection` | 千川爆文合集 | 千川 | `online` | 自动计算 |

种子数据：约 40 条 global 脚本通过 INSERT 写入 `qianchuan_collection_scripts`。

---

## 六、不做清单

- 不做 AI 分析/生成功能
- 不做管理端专属配置 Tab（无 AI 可配）
- 不做达人与 kols 表联动
- 不做导出 Word（下载 .txt 已满足需求）
- 不做脚本编辑（只做增删查）
