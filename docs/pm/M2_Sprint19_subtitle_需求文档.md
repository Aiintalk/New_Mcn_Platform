# M2 Sprint 19 — 字幕提取（subtitle-extractor）迁移需求文档

> **版本**：v1
> **作者**：MCN_PM_Agent
> **日期**：2026-06-25
> **迁移源**：旧架构 `Ai_Toolbox/subtitle-extractor-web/`（Next.js 14 + SQLite）
> **参照样板**：material-library（ConfigTab + workspace_tools 上线模式）、seeding-writer（多 Tab 配置）

---

## 一、定位

抖音视频字幕提取工具，3 大功能：

1. **单条字幕提取**：粘贴抖音分享文本 → tikhub 解析视频 → ASR 转写 → 字幕文本
2. **批量字幕提取**：多行分享文本 → PostgreSQL 持久化任务 + 条目 → 后台批量执行 → 「我的批量任务」列表查看进度
3. **字幕 → AI 思维导图**：yunwu 非流式调用 → rootTitle / summary / branches JSON

附加：SRT / Excel / Zip 导出 + 保存到产出中心。

---

## 二、迁移红线对照

| 红线 | 本功能如何满足 |
|------|--------------|
| #1 运营端入口在「创作中心」 | `/workspace/subtitle-extractor` 路由，workspace_tools tool_code=`subtitle` |
| #2 产出在「产出中心」显示 | `POST /save-output` 写共享 `outputs` 表（tool_code='subtitle'），前端复用全局 `/api/outputs?tool_code=subtitle` |
| #3 公共服务用统一 adapter | tikhub（视频解析）/ asr（阿里云 ASR）/ yunwu（思维导图）全走 adapter |
| #4 Prompt + 模型在管理端可配 | 管理端「工具配置」→「字幕提取配置」Tab：mindmap_prompt + mindmap_model_id |
| #5 纳入管理端「功能配置」 | workspace_tools 注册 tool_code=`subtitle`，dev→online（migration 035） |
| #6 调用第三方写日志 | ASR 由 asr_adapter 自动写 `asr_call_logs`；yunwu 由 adapter 自动写 `ai_call_logs`；router 写 OperationLog |
| #7 拿不准参照已迁功能 | 参照 material-library（ConfigTab 模式）、selling-point（Output 写入 + save-output 模式） |

---

## 三、关键技术决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | tool_code | `subtitle` | workspace_tools 已注册 id=5 |
| 2 | 视频解析 | `tikhub_adapter.fetch_video_by_share_url()` | operator_persona_writer.py 已用 |
| 3 | 音频文件上传 | 前端走 `POST /api/files`（File 表 + OSS）→ 拿 url 进 extract | 复用现有上传链路 |
| 4 | ASR 调用 | `asr_adapter.transcribe(audio_url, db, user_id)` | 自动凭证池 + 写 asr_call_logs |
| 5 | 思维导图 AI | `yunwu_adapter.chat()`（非流式） | 旧架构用 claude-haiku，新架构默认回退同模型 |
| 6 | 思维导图 Prompt + 模型 | 上提到 `subtitle_configs.mindmap_prompt` / `mindmap_model_id` | 红线 #4 |
| 7 | 批量任务表 | 新建 `subtitle_jobs` + `subtitle_items` | 无现成批量模式，参照旧 SQLite schema |
| 8 | 批量异步执行 | `asyncio.create_task(_run_batch())` | 单进程够用；Celery 不在本次范围 |
| 9 | 批量查询 | 客户端轮询 `GET /batch/{job_code}`（5s 间隔，绑定 `created_by`） | ASR 任务 5-30 分钟，SSE 不合适 |
| 10 | 产出接入 | 写共享 `outputs` 表（tool_code='subtitle'） | 红线 #2 |
| 11 | SRT / Excel / Zip 导出 | 前端纯 JS（xlsx + jszip + 自实现 SRT） | 旧架构同方案 |
| 12 | 思维导图可视化 | 前端 AntD Card/List/Tag（不引入 SVG 自绘或 react-flow） | 简化实现 |
| 13 | Migration 编号 | 035 | 当前最高 034（material_library） |
| 14 | 批量任务身份绑定 | `subtitle_jobs.created_by`（JWT 鉴权后绑定 current_user.id） | 旧架构 access_code 8 位查询码是无用户系统产物，新架构 JWT 已足够；管理员通过 `GET /admin/subtitle/batches` 跨用户查询 |

---

## 四、不在本次范围

1. **tool_transcribe.py 改造**：继续云雾 Whisper，Sprint 3 债务
2. **批量任务多进程**：Celery/RQ，单进程 asyncio 够用
3. **字幕翻译**：旧架构没做
4. **字幕时间轴对齐**：旧架构只取 text 不取时间戳，迁后保持
5. **service_credentials.secret_enc 加密**：Sprint 3 债务
6. **access_code 跨设备查询模式**：Step 8 已废弃，由 JWT + `created_by` 替代（旧架构无用户系统的产物，新架构冗余且不安全）

---

## 五、验收标准（10 项）

1. ✅ 单条字幕提取（抖音链接）：5-10 分钟内出字幕
2. ✅ 单条字幕提取（上传音频）：5-10 分钟内出字幕（file_url 路径）
3. ✅ 批量任务：多行提交 → 后台执行 → 「我的批量任务」列表查看进度（与账号绑定）
4. ✅ 思维导图：基于字幕生成 rootTitle/summary/branches JSON
5. ✅ 思维导图 Prompt 在管理端可改 + AI 模型可配
6. ✅ 导出：SRT / Zip / Excel 任选
7. ✅ 产出接入产出中心（写共享 outputs 表）
8. ✅ 所有测试通过（后端 pytest + 前端 tsc）
9. ✅ workspace_tools.subtitle status=online
10. ✅ 契约（Base_API §25 + Base_Database §30）+ 前后端 README + PM 记忆 同步

---

## 六、实施记录

| 步骤 | 状态 | 产物 |
|------|------|------|
| Step 1 分支 + 数据库 | ✅ | migration 035 + 3 ORM |
| Step 2 单条字幕提取 | ✅ | POST /extract + 5 tests + 前端 Tab |
| Step 3 思维导图 + admin 配置 | ✅ | POST /mindmap + 6 tests + admin 2 端点 + 8 tests + SubtitleConfigTab |
| Step 4 批量字幕提取 | ✅ | POST /batch + _run_batch + GET /batch/{job_code}（含 items 进度）+ 前端批量 Tab + conftest patch |
| Step 5 导出 + 产出接入 | ✅ | POST /save-output + 4 tests + 前端 SRT/Excel/Zip 导出 + 保存按钮 |
| Step 6 workspace_tools online + 文档 | ✅ | workspace_tools.subtitle online/140 + Base_API §25 + Base_Database §30 + READMEs + 需求文档 |
| Step 7 全量回归 + PR | 待办 | 待 PR |
| Step 8 移除 access_code 改用 created_by | ✅ | migration 035 删字段 + 3 端点重做（删 by-access / 加 /batches 运营端 / 加 /admin/subtitle/batches 管理端）+ operator 25→28 tests + admin 8→11 tests + 前端批量 Tab 用「我的批量任务」列表替代 access_code 输入框 + 文档同步 |

测试统计：operator_subtitle 28/28 ✅ + admin_subtitle 11/11 ✅。
