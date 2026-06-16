# 千川剪辑预审（qianchuan-edit-review）· 迁移需求文档

> 读者：协作开发者，无需阅读原始代码即可完成实现
> 源码位置：`Ai_Toolbox/qianchuan-edit-review-web/`（Next.js 独立工具）
> 文档状态：Sprint 7 实施完成（2026-06-14）

---

## 一、工具概述

| 项目 | 说明 |
|------|------|
| 原工具路径 | `Ai_Toolbox/qianchuan-edit-review-web/` |
| 功能描述 | 上传原版爆款视频 + 我方成片 → ffmpeg 截帧 → Whisper 转录文案 → 多模态 SSE 流式预审（AI 看画面+文案）→ 导出 Word / 保存报告 |
| AI 模型 | `gpt-4o`（多模态，支持图片输入）|
| 外部依赖 | 云雾 Whisper API（转录）、yunwu adapter（流式对话）|
| 语言 | 中文界面，中文 System Prompt，中文输出 |

**变与不变总结：**
- **不变**：双视频上传界面、System Prompt（硬编码随请求传后端）、多模态消息构建逻辑（帧图片 + 文案交错）、SimpleMarkdown 渲染、Word 导出逻辑
- **变**：加 JWT 认证、截帧和转录从前端 JS 改为后端 API、结果保存到 `outputs` 表、流式对话走统一 yunwu adapter

---

## 二、需求澄清记录（2026-06-14）

| 问题 | 结论 |
|------|------|
| API 路由前缀 | 工具级接口走 `/api/tools/` 前缀，与其他工具一致 |
| 截帧由谁负责 | 后端 ffmpeg subprocess，旧版前端 JS 截帧改为后端接口 |
| 转录由谁负责 | 后端调云雾 Whisper API（httpx），文件大小上限 25MB |
| 转录重试策略 | 429 时重试，`_RETRY_DELAYS=[3,6]`，共 3 次尝试 |
| System Prompt | 硬编码在前端组件中，随 `/chat-stream` 请求传入后端，不做管理端配置 |
| Word 导出 | 后端 python-docx 生成，文件名 URL 编码（RFC 5987），前端下载 |
| 保存报告 | 存入 `outputs` 表，`tool_code='qianchuan-edit-review'` |
| 历史记录 | 本工具不做历史列表页，仅保存（复用产出中心统一查看）|

---

## 三、工作流步骤

| 步骤 | 用户操作 | 系统行为 |
|------|---------|---------|
| **Step 1 · 上传视频** | 左侧上传「原版爆款」视频，右侧上传「我方成片」视频 | 各自存于前端 state，最大 25MB |
| **Step 2 · 截帧 + 转录** | 点击「截帧 + 提取文案」按钮 | 先调 `/api/tools/extract-frames` 获取 base64 帧；再调 `/api/tools/transcribe` 获取文案文本 |
| **Step 3 · 开始预审** | 点击「开始预审」按钮 | 构建多模态消息（文案+帧图片交错），POST `/api/tools/chat-stream`，SSE 流式展示报告 |
| **Step 4 · 导出/保存** | 点击「导出 Word」或「保存报告」| 导出：POST `/api/tools/export-word` 返回 .docx 文件流；保存：POST `/api/tools/qianchuan-edit-review/outputs` |

---

## 四、接口设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/extract-frames` | 上传视频文件，返回 base64 帧列表和时长（ffmpeg 截帧）|
| POST | `/api/tools/transcribe` | 上传视频文件，调云雾 Whisper，返回转录文本 |
| POST | `/api/tools/chat-stream` | 通用多模态 SSE 流式接口，透传 messages + system_prompt |
| POST | `/api/tools/export-word` | Markdown → .docx 文件流，文件名 URL 编码 |
| POST | `/api/tools/qianchuan-edit-review/outputs` | 保存报告到 outputs 表，返回 `{id, created_at}` |

**关键规则：**
- 所有接口需 JWT 鉴权（`require_password_changed`）
- 截帧接口：ffprobe 读时长，ffmpeg 逐帧截图（720px 宽），超时 60s
- 转录接口：文件 > 25MB 返回 400 FILE_TOO_LARGE
- chat-stream：`messages` 为空或 `system_prompt` 为空返回 400 INVALID_INPUT
- export-word：`content` 为空返回 400 INVALID_INPUT；文件名格式 `千川预审报告_{YYYYMMDD}.docx`
- 非流式/非文件接口必须返回标准信封 `success_response(data=...)`（红线 #1）

---

## 五、多模态消息构建逻辑

System Prompt 存于前端组件常量，随请求发送后端：

```
你是千川广告剪辑预审专家。同时分析原版爆款和我方成片的画面帧 + 文案，
给出仅限剪辑层面（不涉及重拍/重写）的优化建议。
输出格式：开头剪辑 / 时长与删减 / 节奏问题 / 画面插入建议 / 核心问题 Top3 / 剪辑修改清单
```

消息体结构（content 为 array，多模态）：
```
[text: 原版文案和时长] + [text: 原版第Xs:] + [image_url: base64帧] × N
[text: 我方文案和时长] + [text: 我方第Xs:] + [image_url: base64帧] × N
```

---

## 六、数据库

**无新增表**（仅注册 workspace_tools 入口）

| 迁移文件 | 操作 |
|---------|------|
| `migrations/019_qianchuan_edit_review.sql` | INSERT INTO workspace_tools (qianchuan-edit-review, 千千剪辑预审, 千川, online) |

---

## 七、迁移规范合规清单

| 红线 | 状态 |
|------|------|
| 红线 1：入口在创作中心 | ✅ workspace_tools 已注册，status=online |
| 红线 2：产出接入产出中心 | ✅ 存 outputs 表，tool_code='qianchuan-edit-review' |
| 红线 3：AI 走统一 adapter | ✅ yunwu_adapter.chat_stream |
| 红线 4：Prompt 写进代码 | ✅ 前端硬编码常量（本工具无需管理端配置）|
| 红线 5：纳入功能配置 | ✅ workspace_tools 已注册 |
| 红线 6：调用写日志 | ✅ yunwu_adapter 内置写 ai_call_logs |

---

## 八、不做清单

- 不做历史记录列表页（产出中心统一查看）
- 不把 System Prompt 移到管理端配置（本工具固定 Prompt）
- 不在后端保存截帧图片（仅在请求中传递 base64，不持久化）
- 不做并发截帧（帧逐个顺序执行，避免 ffmpeg 资源竞争）
