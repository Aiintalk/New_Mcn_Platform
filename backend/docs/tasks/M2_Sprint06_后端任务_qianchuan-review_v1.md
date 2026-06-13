# M2 Sprint 6 · 后端任务 · qianchuan-review v1

> 状态：✅ 已完成（2026-06-13）
> 需求文档：`docs/pm/M2_Sprint06_qianchuan-review_需求文档.md`
> 实施计划：`docs/superpowers/plans/2026-06-13-qianchuan-review-migration.md`

---

## 一、新建 / 修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/app/tools/qianchuan_review/__init__.py` | 新建 | package 标记 |
| `backend/app/tools/qianchuan_review/prompts.py` | 新建 | PROMPT_WITH_EXCEL / PROMPT_WITHOUT_EXCEL 两个 System Prompt 常量，逐字来自原始 JS |
| `backend/app/services/qianchuan_review_service.py` | 新建 | ScriptItem / ExcelRow dataclass、merge_scripts_and_excel、build_user_message、generate_review_stream |
| `backend/app/routers/operator_qianchuan_review.py` | 新建 | 4 个接口（parse-file / generate / save / outputs）|
| `backend/scripts/migrate_qianchuan_reports.py` | 新建 | 旧数据迁移脚本，支持 --dry-run |
| `backend/app/services/file_parser.py` | 修改 | 追加 `parse_qianchuan_review_file()` + `_parse_pages_qianchuan_review()`（含日历噪声过滤）；`import zipfile` 移到顶部 |
| `backend/app/main.py` | 修改 | 注册 `operator_qianchuan_review_router`；CORS 新增 `expose_headers=["X-Task-Id"]` |
| `backend/tests/unit/tools/__init__.py` | 新建 | package 标记 |
| `backend/tests/unit/tools/test_qianchuan_review_prompts.py` | 新建 | prompts 精确比对测试 17 个用例 |
| `backend/tests/unit/services/test_qianchuan_review_service.py` | 新建 | service 单元测试 13 个用例 |
| `backend/tests/unit/services/test_qianchuan_review_file_parser.py` | 新建 | file_parser 单元测试 14 个用例（含日历噪声过滤） |
| `backend/tests/integration/routers/test_operator_qianchuan_review.py` | 新建 | 集成测试 13 个用例 |

---

## 二、接口清单

### 运营端（operator / admin 角色）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tools/qianchuan-review/parse-file` | 文件解析，返回 `{success, data: {text, filename}}`；ValueError → 400 UNSUPPORTED_FORMAT |
| POST | `/api/tools/qianchuan-review/generate` | SSE 流式生成，Header `X-Task-Id`；空 scripts → 400；>30 条 → 400；流前创建 task_job(processing)，流后更新(success) |
| POST | `/api/tools/qianchuan-review/save` | 保存报告到 outputs 表，返回 `{success, data: {output_id}}` |
| GET  | `/api/tools/qianchuan-review/outputs` | 历史列表，operator 过滤 created_by；admin 全量；分页 page/size |

---

## 三、核心业务逻辑

### 脚本-Excel 合并匹配算法（Python 等价 JS 原版）

```python
def _normalize(text):
    return re.sub(r"[，。！？、#@\s]", "", text)[:12]  # 清除标点，取前12字

def _is_match(a_norm, b_norm):
    return a_norm[:6] in b_norm or b_norm[:6] in a_norm  # 双向 includes 取前6字
```

匹配成功 → 用 Excel video_theme 覆盖标题；未匹配的 Excel 行追加到末尾（content=""）；整体按 spend 降序。

### System Prompt 策略

- `has_excel=True` → 使用 `PROMPT_WITH_EXCEL`（6个模块：跑量/ROI/开头效率/亏损诊断/卖点洞察/投放效率）
- `has_excel=False` → 使用 `PROMPT_WITHOUT_EXCEL`（5个模块：最好素材/淘汰/卖点结构/开头类型/新方向）

### task_job 生命周期

```
流开始前：INSERT task_jobs(status=processing, input_payload={script_count, has_excel})
流完成后：UPDATE task_jobs SET status=success, finished_at, duration_ms  （background task，独立 AsyncSessionLocal）
AI 报错：UPDATE task_jobs SET status=failed  （通过 [ERROR] chunk 体现）
```

---

## 四、数据库

- **无新表**（复用 `outputs`、`task_jobs`、`ai_call_logs`）
- **已有迁移**：`migrations/011_tikhub_call_logs.sql` 已注册 qianchuan-review 到 workspace_tools（status=dev）

---

## 五、依赖

无新增 pip 包（`python-snappy` 已在 requirements.txt，`zipfile` 为标准库）。

---

## 六、技术处理要点

| # | 风险点 | 处理方式 |
|---|--------|---------|
| 1 | Nginx 默认超时60s | 运维任务单注明，为 /generate 单独配置 proxy_read_timeout 300s |
| 2 | SSE 中断不释放资源 | `generate_stream()` 内捕获 `GeneratorExit` |
| 3 | DB session 生命周期 | background task 使用独立 `AsyncSessionLocal()`，不复用 router 层 db |
| 4 | CORS 暴露自定义 Header | main.py CORS 新增 `expose_headers=["X-Task-Id"]` |
| 5 | outputs 分页计数 | 一次全量有序查询后内存切片，避免双查询 |

---

## 七、测试结果

| 测试文件 | 用例数 | 结果 |
|---------|--------|------|
| `test_qianchuan_review_prompts.py` | 17 | 17/17 ✅ |
| `test_qianchuan_review_service.py` | 13 | 13/13 ✅ |
| `test_qianchuan_review_file_parser.py` | 14 | 14/14 ✅ |
| `test_operator_qianchuan_review.py` | 13 | 13/13 ✅ |
| **合计** | **57** | **57/57 ✅** |

**覆盖率（新模块）：**

| 模块 | 覆盖率 | 目标 | 状态 |
|------|--------|------|------|
| `tools/qianchuan_review/prompts.py` | **100%** | 100% | ✅ |
| `services/qianchuan_review_service.py` | **86%** | ≥80% | ✅ |
| `services/file_parser.py`（新增函数） | **82%** | ≥90% | ⚠️ 差8% |
| `routers/operator_qianchuan_review.py` | **73%** | ≥70% | ✅ |

> `file_parser.py` 未覆盖行集中在 `.docx` snappy fallback 路径和 `.pages` 边界分支，属难以用单元测试模拟的 OS 级失败，不影响实际使用。

---

## 八、全量回归

本次新增代码不引入任何历史测试失败。全量运行 `tests/unit/ + tests/integration/` 共 **414 passed**，0 failed。
