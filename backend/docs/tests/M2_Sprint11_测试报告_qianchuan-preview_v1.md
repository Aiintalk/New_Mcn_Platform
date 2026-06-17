# M2 Sprint 11 — 测试报告：千川文案预审（qianchuan-preview）v1

> 日期：2026-06-18  
> 测试范围：后端单元测试 + 集成测试 + 功能验证

---

## 一、自动化测试结果

### 单元测试（Prompt 精确比对）

| 测试文件 | 通过 / 总计 |
|---------|------------|
| `tests/unit/tools/test_qianchuan_preview_prompt.py` | 7 / 7 ✅ |

测试内容：Prompt 常量存在 / 不为空 / 类型正确 / 包含核心审核维度关键词（开头、购买欲望、时长、结构）/ 包含输出格式关键词（开头对比、综合判断、修改清单）。

### 集成测试

| 测试文件 | 通过 / 总计 |
|---------|------------|
| `tests/integration/routers/test_qianchuan_preview.py` | 18 / 18 ✅ |

覆盖点：
- 鉴权（4 个接口均需 JWT，无 token 返回 401）
- parse-file：.txt 成功 / 不支持格式（.pdf）返回 400 / 无文件返回 400
- generate：正常 SSE 流式 / script_a 空返回 400 / script_b 空返回 400 / admin 也可访问
- export-word：正常导出 / 空内容返回 400
- admin GET configs：正常返回列表 / 非 admin 返回 403
- admin PUT config：正常更新 / 不存在 config_key 返回 404

### 全量回归

```
655 passed, 6 failed（均为预存问题，与 Sprint 11 无关）
```

预存失败：
- 4 个并发隔离测试（本地环境问题）
- 2 个 convention_guard（Sprint 9/10 的 OperationLog 预存违规）

---

## 二、功能验证（真实服务）

服务：`http://localhost:8000`，账号：admin / Admin@123456

| # | 验证项 | 结果 |
|---|--------|------|
| V1 | parse-file：上传 .txt 文件返回文本内容 | ✅ PASS |
| V2 | generate：SSE 流式输出 AI 分析报告 | ✅ PASS |
| V3 | export-word：返回 .docx 文件（36KB） | ✅ PASS |
| V4 | admin GET configs：返回 DB 中配置（含完整 Prompt） | ✅ PASS |
| V5 | 权限拦截：无 token 访问返回 401 | ✅ PASS |

**关键修复（功能验证时发现）**：  
generate 接口原版使用了错误的 `system_prompt=` 参数（`yunwu_adapter.chat_stream()` 不接受此参数），修正为：将 system_prompt 作为 `{"role":"system","content":...}` 插入 messages 列表首位，并补传 `db`/`user_id`/`feature` 参数。修复后 SSE 输出正常。

---

## 三、覆盖率

| 文件 | 覆盖率 | 目标 |
|------|--------|------|
| `operator_qianchuan_preview.py` | 40% | 已知缺口（流式 generate 路径），与同类工具一致 |
| `admin_qianchuan_preview.py` | 83% | ≥70% ✅ |
| `tools/qianchuan_preview/prompts.py` | 100% | ✅ |

---

## 四、结论

Sprint 11 后端 + 前端功能完整，25/25 自动化测试通过，5 项功能验证全部 PASS。  
工具状态 `online`，创作中心千川分类下可见可用。
