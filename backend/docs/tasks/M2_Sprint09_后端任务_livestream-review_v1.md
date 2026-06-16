# M2 Sprint 9 — 后端任务：直播间脚本复盘（livestream-review）

> 状态：✅ 已完成  
> 完成日期：2026-06-15  
> 分支：`0615_livestream-review`（已合并 main）

---

## 一、任务范围

| 文件 | 说明 |
|------|------|
| `backend/migrations/020_livestream_review.sql` | 建 `livestream_review_configs` 表，注册 workspace_tools（status=dev） |
| `backend/app/models/livestream_review.py` | LivestreamReviewConfig ORM 模型 |
| `backend/app/models/__init__.py` | 注册新模型 |
| `backend/app/tools/livestream_review/prompts.py` | PROMPT_WITH_EXCEL / PROMPT_WITHOUT_EXCEL 原文（zero-diff） |
| `backend/app/tools/livestream_review/service.py` | merge_scripts_and_excel / detect_has_excel / build_user_message / generate_review_stream |
| `backend/app/services/file_parser.py` | 新增 parse_livestream_review_file()（复用 qianchuan_review 逻辑） |
| `backend/app/routers/operator_livestream_review.py` | 4 个接口：parse-file / generate / save / outputs |
| `backend/app/routers/admin_livestream_review.py` | 2 个接口：GET/PUT configs（管理端 Prompt+模型配置） |
| `backend/app/main.py` | 注册两个 router |
| `backend/tests/conftest.py` | 注册 operator_livestream_review.AsyncSessionLocal |

## 二、接口清单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/livestream-review/parse-file` | 解析脚本文件（.txt/.md/.docx/.pages） |
| POST | `/api/tools/livestream-review/generate` | 流式生成复盘报告（StreamingResponse），写 task_jobs |
| POST | `/api/tools/livestream-review/save` | 保存报告到 outputs 表，写 OperationLog |
| GET  | `/api/tools/livestream-review/outputs` | 查当前用户历史报告（分页） |
| GET  | `/api/admin/livestream-review/configs` | 管理端：查配置列表 |
| PUT  | `/api/admin/livestream-review/configs/{key}` | 管理端：更新配置 |

## 三、关键设计决策

- **Prompt 存 DB**：遵迁移红线 #4，两版 Prompt（with_excel / without_excel）存 `livestream_review_configs`，管理端可改
- **hasExcel 判断**：后端合并后检查 merged_list 是否含 gmv/peak_viewers/conversions，非简单判断 excel_data 非空
- **未匹配 Excel 行不追加**：只发有脚本内容的场次给 AI（Q9 决策）
- **GMV 降序排列**：后端排序
- **流式日志**：finally 块更新 task_jobs（success/error）

## 四、测试覆盖

| 文件 | 测试数 | 覆盖率 |
|------|--------|--------|
| `test_livestream_review_prompts.py` | 16 | Prompt 精确比对 |
| `test_livestream_review_service.py` | 22 | merge/detect/build 单元测试 |
| `test_operator_livestream_review.py` | 20 | 集成测试（auth/parse/generate/save/outputs/admin） |
| `operator_livestream_review.py` 覆盖率 | — | 86% ✅（目标 ≥70%） |
| `admin_livestream_review.py` 覆盖率 | — | 86% ✅ |
| `service.py` 覆盖率 | — | 72%（流式路径测试库难覆盖，已知缺口） |
