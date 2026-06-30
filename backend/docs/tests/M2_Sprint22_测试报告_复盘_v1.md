# M2 Sprint22 测试报告 — 复盘（retrospective）v1

> 分支：`feature/kol-workspace`
> 测试时间：2026-06-27
> 测试环境：本地 macOS / PostgreSQL 18.4 @ localhost:5432 / Python 3.10

---

## 一、测试总览

| 层次 | 文件 | 通过/总数 | 结果 |
|------|------|-----------|------|
| 后端集成测试 | `test_operator_retrospective.py` | 13 / 13 | ✅ |
| 前端组件测试 | `WorkspaceRetrospective.test.tsx` | 6 / 6 | ✅ |
| **合计** | | **19 / 19** | ✅ |

---

## 二、后端测试详情

### 文件：`tests/integration/routers/test_operator_retrospective.py`

运行命令：
```bash
cd backend && .venv/bin/python -m pytest tests/integration/routers/test_operator_retrospective.py -v
```

| # | 测试用例 | 结果 |
|---|---------|------|
| 1 | test_no_token → 401 | ✅ |
| 2 | test_admin_get_config → 返回 default 配置 | ✅ |
| 3 | test_admin_put_config → 更新成功 | ✅ |
| 4 | test_list_sessions_empty → 空列表 | ✅ |
| 5 | test_create_session → 返回 session 对象（含 id/title/status=draft） | ✅ |
| 6 | test_list_sessions_after_create → 列表包含新建记录 | ✅ |
| 7 | test_update_session → 更新 title/live_data 后返回最新内容 | ✅ |
| 8 | test_delete_session → success | ✅ |
| 9 | test_delete_session_not_found → 404 | ✅ |
| 10 | test_parse_files → 返回解析文本（mock document_parser） | ✅ |
| 11 | test_analyze_stream → SSE 响应（mock yunwu_adapter） | ✅ |
| 12 | test_analyze_sets_status_done → analyze 完成后 status 改为 done | ✅ |
| 13 | test_export_word → 返回 docx 字节流（Content-Type 正确） | ✅ |

**覆盖路径**：
- 鉴权拦截（未登录 / 未改密）
- 管理端 GET/PUT config
- 运营端全部 7 个接口（list / create / update / delete / parse-files / analyze / export-word）
- analyze 完成后自动写 result + 改 status=done
- 404 异常路径（delete 不存在记录）

---

## 三、前端测试详情

### 文件：`src/__tests__/components/pages/WorkspaceRetrospective.test.tsx`

运行命令：
```bash
cd frontend && PATH=/opt/homebrew/opt/node@26/bin:$PATH npx vitest run src/__tests__/components/pages/WorkspaceRetrospective.test.tsx
```

| # | 测试用例 | 结果 |
|---|---------|------|
| 1 | 渲染历史列表视图（列表空时提示「暂无复盘记录」） | ✅ |
| 2 | 点击「+ 新建复盘」切换到编辑视图 | ✅ |
| 3 | 编辑视图填写标题 + 直播数据后点「保存草稿」触发 upsertSession | ✅ |
| 4 | 「开始复盘分析」触发 analyzeStream（mock）→ 流式文本出现 | ✅ |
| 5 | 点击历史记录进入详情视图 | ✅ |
| 6 | RetrospectiveConfigTab 渲染 system_prompt TextArea + 保存 | ✅ |

---

## 四、全量回归

Sprint 22 提交后，后端全量回归结果：

```
1098 passed, 9 failed, 1 error（212.92s）
```

9 个失败 + 1 个 error 均为预存技术债，与 Sprint 22 改动无关：
- 并发隔离测试 7 个（本地 asyncpg 环境问题，测试服可通过）
- `test_operator_subtitle::TestBatch::test_batch_create_success` 1 个（预存）
- `test_qianchuan_review_prompts::test_prompts_are_different` error 1 个（预存）

前端全量回归（macOS 本地环境）：
```
192 passed（193 total，1 个预存 SeedingWriter 用例超时），5 个文件预存失败（persona / Asr / Oss / authStore）
```

---

## 五、不在测试范围

- analyze 时 AI Key 池耗尽 / 流式中断场景（依赖真实 AI 调用）
- material_scripts JSONB 多文件解析后的并发写入
- export-word 中文文件名 URL 编码（Word 文件名固定为 `retrospective.docx`）
- 物理删除的不可恢复性（业务已决策，无需软删）
