# M2 Sprint 10 — 后端任务：人设脚本复盘（persona-review）

> 状态：进行中  
> 迁移来源：`Ai_Toolbox/persona-review-web`  
> 路由前缀：`/api/tools/persona-review`  
> 覆盖率目标：service ≥ 80%，router ≥ 70%

---

## 一、任务清单

| # | 任务 | 文件 | 说明 |
|---|------|------|------|
| B1 | 数据库迁移 | `migrations/023_persona_review.sql` | 创建 persona_review_configs 表 + workspace_tools 注册 |
| B2 | System Prompt | `app/tools/persona_review/prompts.py` | 两版 Prompt 原文零改动（hasExcel A/B） |
| B3 | 服务层 | `app/tools/persona_review/service.py` | 合并逻辑 / hasExcel / user_message / stream |
| B4 | 运营端路由 | `app/routers/operator_persona_review.py` | 3 个接口：generate / save / outputs |
| B5 | 管理端路由 | `app/routers/admin_persona_review.py` | 2 个接口：GET/PUT configs |
| B6 | main.py 注册 | `app/main.py` | import + include_router |
| B7 | conftest.py 注册 | `tests/conftest.py` | operator_persona_review 无 AsyncSessionLocal，无需注册 |
| B8 | 单元测试 | `tests/unit/tools/test_persona_review_prompts.py` | Prompt 精确比对 |
| B9 | 单元测试 | `tests/unit/tools/test_persona_review_service.py` | merge/hasExcel/user_message 逻辑 |
| B10 | 集成测试 | `tests/integration/routers/test_operator_persona_review.py` | 3 个接口的请求/响应验证 |

---

## 二、关键约束（与 livestream-review 的差异）

| 差异点 | persona-review |
|--------|----------------|
| 无 parse-file 接口 | txt 前端直读，不调后端 |
| 匹配字段 | `video_theme`（非 live_theme） |
| Excel 侧清洗 | `re.sub(r'[，。！？、\s　]', '', s)` （无 #@） |
| 脚本侧清洗 | `re.sub(r'[，。！？、#@\s　]', '', s)` （有 #@） |
| 未匹配 Excel 行 | **追加到末尾**（content=""），与 livestream 不同 |
| 排序依据 | 点赞数降序（`int(likes or '0')`） |
| 内容截断 | **2000 字**（非 3000） |
| hasExcel 判断字段 | completion_rate \| ad_spend \| likes |

---

## 三、接口设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/persona-review/generate` | 流式生成，StreamingResponse，X-Task-Id header |
| POST | `/api/tools/persona-review/save` | 保存到 outputs 表 |
| GET  | `/api/tools/persona-review/outputs` | 历史列表，当前用户，分页 |
| GET  | `/api/tools/admin/persona-review/config` | 管理端读取配置 |
| PUT  | `/api/tools/admin/persona-review/config` | 管理端更新配置 |
