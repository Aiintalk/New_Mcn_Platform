# 产品卖点提取器（selling-point-extractor）· 迁移需求文档

> 读者：协作开发者，无需阅读原始代码即可完成实现
> 源码位置：`Ai_Toolbox/selling-point-extractor-web/`
> 文档状态：需求澄清完成（2026-06-13），Sprint 5 实施完成（2026-06-13）

---

## 一、工具概述

| 项目 | 说明 |
|------|------|
| 原工具路径 | `Ai_Toolbox/selling-point-extractor-web/` |
| 原部署端口 | 3011，basePath `/selling-point-extractor` |
| 功能描述 | 上传产品 Brief 文档 + 达人文案脚本（均可多文件），AI 提炼极致卖点卡（机制/背书/口碑/产品力四板块），支持多轮追问迭代，自动保存历史记录，最终下载 .md 卖点卡 |
| AI 模型 | 管理端可配置（`selling_point_configs` 表，config_key='extract'），默认兜底 `claude-sonnet-4-6` |
| 外部依赖 | 无（无 TikHub / OSS / ASR） |
| 语言 | 中文界面，中文 System Prompt，中文输出 |

**变与不变总结：**
- **不变**：所有工作流步骤、消息裁剪逻辑（留前端）、.md 导出（留前端）、文件解析格式支持
- **变**：加 JWT 认证、历史记录改存 `outputs` 表（原为本地 JSON 文件）、AI 调用改走 `credentials` 表 Key 池、**Prompt 和模型上提到管理端可配置**（满足迁移红线 4）
- **清零**：线上服务器历史数据不迁移，新系统重新积累

---

## 二、需求澄清记录（2026-06-13）

| 问题 | 结论 |
|------|------|
| Prompt/模型是否需要管理端可配置？ | **是**，新建 `selling_point_configs` 表，管理端可配置 |
| 产出是否接入产出中心？ | **是**，存 outputs 表，产出中心按 tool_code 展示 |
| 历史产品名如何提取？ | 保持旧逻辑（前端正则提取，不准则默认「未命名产品」） |
| 历史记录权限 | 全员共享，不按用户隔离 |
| 历史记录删除 | 软删除（设 deleted_at），不物理删除 |
| .pages 解析模块 | 独立函数 `parse_selling_point_file()`，中文≥5 过滤，无日历噪音过滤 |

---

## 三、工作流步骤（3步，完全保留）

| 步骤 | 用户操作 | 系统行为 |
|------|---------|---------|
| **Step 1 · 上传 Brief** | 上传产品 Brief 文件（可多个）或粘贴文本；可跳过 | 调 `/api/tools/selling-point-extractor/parse-file` 解析 |
| **Step 2 · 上传达人文案** | 上传达人脚本文件（可多个）或粘贴文本 | 同上 |
| **Step 3 · 生成+追问** | 点击"开始提取卖点" → 查看 → 追问 → 下载 .md | 调 `/api/tools/selling-point-extractor/chat` 流式生成；完成后自动保存历史 |

---

## 四、迁移规范合规清单

| 红线 | 状态 |
|------|------|
| 红线 1：入口在创作中心 | ✅ WorkspacePage + workspace_tools 注册 |
| 红线 2：产出接入产出中心 | ✅ 存 outputs 表，tool_code='selling-point-extractor' |
| 红线 3：AI 走统一 adapter | ✅ yunwu_adapter.chat_stream |
| 红线 4：Prompt+模型管理端可配置 | ✅ selling_point_configs 表 + 管理端 Tab |
| 红线 5：纳入功能配置 | ✅ workspace_tools 插入，status=online |
| 红线 6：调用写日志 | ✅ yunwu_adapter 内置写 ai_call_logs |

---

## 五、不做清单

- 不迁移历史记录数据
- 不添加文件大小限制
- 不把消息裁剪逻辑移到后端
- 不把 .md 导出改为经过后端
