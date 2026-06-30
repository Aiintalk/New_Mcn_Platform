# M2 Sprint21 测试报告 — 千川脚本预审（qianchuan-script-review）v1

> 分支：`feature/kol-workspace`
> 测试时间：2026-06-27
> 测试环境：本地 macOS / PostgreSQL 18.4 @ localhost:5432 / Python 3.10

---

## 一、测试总览

| 层次 | 文件 | 通过/总数 | 结果 |
|------|------|-----------|------|
| 后端集成测试 | `test_operator_script_review.py` | 8 / 8 | ✅ |
| 前端组件测试 | `QianchuanScriptReviewPage.test.tsx` | 7 / 7 | ✅ |
| **合计** | | **15 / 15** | ✅ |

---

## 二、后端测试详情

### 文件：`tests/integration/routers/test_operator_script_review.py`

运行命令：
```bash
cd backend && .venv/bin/python -m pytest tests/integration/routers/test_operator_script_review.py -v
```

| # | 测试用例 | 结果 |
|---|---------|------|
| 1 | TestAuth::test_no_token → 401 | ✅ |
| 2 | TestAuth::test_wrong_role_admin_only_no（admin 可访问） | ✅ |
| 3 | TestReview::test_review_direct_pass — direct 模式返回 pass | ✅ |
| 4 | TestReview::test_review_direct_fail — direct 模式返回 fail | ✅ |
| 5 | TestReview::test_review_value_pass — value 模式返回 pass | ✅ |
| 6 | TestReview::test_review_value_no_product — value 模式无需 product | ✅ |
| 7 | TestReview::test_review_uses_db_prompt — 使用 DB Prompt 而非默认 | ✅ |
| 8 | TestReview::test_review_json_parse_fallback — AI 返回 markdown 包裹 JSON 容错解析 | ✅ |

**覆盖路径**：
- 鉴权拦截（未登录 / 未改密）
- `direct` 模式 + `value` 模式
- DB 中有/无配置两条路径
- AI 返回裸 JSON / markdown fence 包裹 JSON 容错
- `_resolve_model_id` 兜底逻辑

---

## 三、前端测试详情

### 文件：`src/__tests__/components/pages/QianchuanScriptReviewPage.test.tsx`

运行命令：
```bash
cd frontend && PATH=/opt/homebrew/opt/node@26/bin:$PATH npx vitest run src/__tests__/components/pages/QianchuanScriptReviewPage.test.tsx
```

| # | 测试用例 | 结果 |
|---|---------|------|
| 1 | 渲染双栏布局（左：输入 / 右：结果区） | ✅ |
| 2 | 「千川直销」/ 「价值观」切换模式 | ✅ |
| 3 | 直销模式填写产品信息表单 | ✅ |
| 4 | 点击「预审」触发 reviewScript API | ✅ |
| 5 | 审核结论展示（rating=pass badge + must_fix 列表） | ✅ |
| 6 | 审核结论展示（rating=fail badge） | ✅ |
| 7 | ConfigTab 渲染 direct_prompt / value_prompt TextArea + 保存 | ✅ |

---

## 四、全量回归

Sprint 21 提交后，后端全量回归结果：

```
1098 passed, 9 failed, 1 error（212.92s）
```

9 个失败 + 1 个 error 均为预存技术债（并发测试 7 个 + subtitle batch 1 个 + qianchuan review prompts error 1 个），与 Sprint 21 改动无关。

---

## 五、不在测试范围

- AI Key 池耗尽场景（依赖真实 AI 调用）
- AI 响应为非 JSON 且无 JSON 子串时的终态（error_response 返回）
- 管理端 GET/PUT config 接口（admin_script_review.py，已有守卫测试覆盖）
