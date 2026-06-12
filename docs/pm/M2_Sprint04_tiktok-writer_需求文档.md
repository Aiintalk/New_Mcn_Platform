# M2 Sprint 04 · TikTok 脚本仿写（tiktok-writer）需求文档

> 创建时间：2026-06-12
> 状态：✅ 开发完成，已推送远端

---

## 一、工具概述

| 项目 | 说明 |
|------|------|
| tool_code | `tiktok-writer` |
| 原工具路径 | `Ai_Toolbox/tiktok-writer-web/` |
| 功能描述 | 输入 TikTok 视频文案，AI 分析开头钩子 + 结构，仿写新的 Body，支持多轮迭代修改，最终导出 Word 文档 |
| AI 模型 | `claude-opus-4-6-thinking`（默认），前端可传入 model 参数覆盖 |
| 外部依赖 | 无（无 TikHub / OSS / ASR） |
| 语言 | 英文界面、英文 System Prompt、英文输出 |

**变与不变：**
- **不变**：所有工作流步骤、System Prompt 原文、前端交互逻辑、点赞数校验（≥10万）、字数校验逻辑
- **变**：加 JWT 认证、AI 调用改走 credentials 表 Key 池、写 task_jobs + outputs 审计、达人列表改查 kols 表

---

## 二、工作流（5 步）

| 步骤 | 用户操作 | 系统行为 |
|------|---------|---------|
| Step 1 · Source | 粘贴 TikTok 链接（仅记录）；粘贴文案；填写点赞数 | 前端校验点赞数 ≥ 100,000 |
| Step 2 · Validate | 点击"Evaluate Opening Hook"；从列表选择创作者人设（可跳过） | AI 分析开头，流式返回 PASS/FAIL + 原因 |
| Step 3 · Structure | 点击"Analyze Structure" | AI 分析结构，前端解析锁定 Opening |
| Step 4 · Rewrite | 选择模式（AI 直写 / 用户提供方向）→ 生成 Body → 多轮对话修改 | 流式仿写 Body，写 task_jobs 审计 |
| Step 5 · Export | 可直接编辑 finalBody → 点击导出 Word | 返回 .docx 二进制，写 outputs 表 |

---

## 三、API 接口

| 接口 | 说明 |
|------|------|
| `POST /api/tools/tiktok-writer/chat` | JWT 鉴权；raw text stream；429 重试 3 次（指数退避 2/4/6s）；写 ai_call_logs |
| `POST /api/tools/tiktok-writer/export-word` | JWT 鉴权；返回 docx 二进制；写 outputs 表 |
| `GET /api/tools/tiktok-writer/kols/personas` | JWT 鉴权；查 kols 表返回人设列表（soul/contentPlan 兼容旧格式） |

---

## 四、数据库

无新表。使用已有表：`task_jobs`、`outputs`、`ai_call_logs`、`kols`。
workspace_tools 新增一条（migration 014_tiktok_writer.sql）。

---

## 五、不做清单（已冻结）

- 不实现历史记录功能
- 不实现文件上传
- 不修复有序列表渲染 bug（原版行为保留）
- 不添加服务端字数校验

---

## 六、需求澄清记录（2026-06-11）

| 问题 | 结论 |
|------|------|
| model 参数是否限制 | 前端可传，后端照单全收 |
| outputs 写入时机 | 每次 Generate Body（首次生成）写一条 task_job，导出时写 outputs |
| 达人列表接口设计 | 本工具专属接口，不与其他工具共用 |
| Word 导出模块 | 建共用 `app/services/word_export.py`，tiktok-writer 首用 |
