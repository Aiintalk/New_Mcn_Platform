# M2 Sprint 11 — 千川文案预审（qianchuan-preview）需求文档

> 文档状态：已完成  
> 完成日期：2026-06-18  
> 来源：功能迁移自旧工具箱 `Ai_Toolbox_new/qianchuan-preview-web/`

---

## 一、功能概述

**工具名称**：千川文案预审  
**工具代码**：`qianchuan-preview`  
**分类**：千川  
**路由**：`/workspace/qianchuan-preview`  
**状态**：online（迁移时直接上线）

**核心流程**：上传/粘贴两段文案（原版爆款 + 我方文案）→ AI 流式对比分析 → 生成预审报告 → 导出 Word / 复制

---

## 二、功能需求

### 2.1 输入方式（双侧对称）
- 文案A（原版爆款）、文案B（我方文案）两侧各自独立
- 支持上传文档（`.txt` / `.docx`，通过后端 parse-file 接口解析）
- 支持直接粘贴文本到 textarea
- 两者互不干扰，可独立清除

### 2.2 AI 分析
- 两侧文案均有内容后可触发「开始预审」
- SSE 流式输出，逐字呈现分析结果
- System Prompt 从管理端 DB 读取，管理员可配置

### 2.3 报告操作
- 复制报告内容到剪贴板
- 导出 Word（后端 export-word 接口生成 .docx）
- 不保存历史（轻量工具，无历史管理）

### 2.4 管理端
- 管理员可配置 System Prompt 和 AI 模型
- 路径：管理端工作台配置 → 千川文案预审 Tab

---

## 三、与旧工具的差异点

| 维度 | 旧工具（Next.js） | 新平台 |
|------|------------------|-------|
| Prompt 存储 | 硬编码在前端 `page.tsx` | DB（`qianchuan_preview_configs`），管理端可配 |
| 文件解析 | 前端 mammoth.js（仅 .docx/.txt） | 后端 `parse-file` 接口（复用 `parse_qianchuan_review_file`，含 .pages 支持） |
| 模型配置 | 硬编码 | 管理端可配 `ai_model_id` |
| 历史记录 | 无 | 无（保持一致） |
| 鉴权 | 无 | JWT（operator/admin） |

---

## 四、接口概览

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/tools/qianchuan-preview/parse-file` | POST | 文档解析，返回文本 |
| `/api/tools/qianchuan-preview/generate` | POST | SSE 流式 AI 预审 |
| `/api/tools/qianchuan-preview/export-word` | POST | 导出 Word 文件 |
| `/api/admin/qianchuan-preview/configs` | GET | 管理端获取配置列表 |
| `/api/admin/qianchuan-preview/configs/{config_key}` | PUT | 管理端更新配置 |

---

## 五、不做清单

- 不做历史记录保存（旧工具无此功能，保持一致）
- 不做多轮追问（预审是一次性输出）
- 不做 PDF 导出
