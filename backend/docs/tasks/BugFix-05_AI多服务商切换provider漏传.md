# MCN_PM_Agent — BugFix-05 任务与验收（AI 多服务商切换 provider 漏传 + siliconflow 空 choices IndexError）

> 角色：MCN_PM_Agent（PM + 跨端开发）
> 工作目录：`backend/`
> PM 生成时间：2026-07-03（**事后补写**——本任务单在 PR 已合并后才补，原因见末尾"事后补写说明"）
> 完成时间：2026-07-03
> 优先级：P0（admin 配置完全无效 + siliconflow 调用直接崩）
> 对应 commit：`ce1f7c1`（PR #19，已合并到 main，merge commit `a07c48b`）
> 分支：`fix/ai-provider-switch`（已删除）
> 状态：**已完成 + 已合并 main**

---

## 一、Bug 描述

### Bug-A：admin 切厂商不生效（P0）

**现象**：admin 在「工具配置 → 卖点提取（或其他工具）」切换到 siliconflow 模型并保存后，运营端调用 AI 仍走 yunwu。

**用户原话反馈**：「我在服务器上切换了厂商模型不生效」。

### Bug-B：切到 siliconflow 后报 list index out of range（P0）

**现象**：用户强制切到 siliconflow 后，调用 AI 报错 `[siliconflow]: list index out of range`。

**用户原话反馈**：「修复成功后有：[ERROR] chat_stream failed [siliconflow]: list index out of range 的问题」。

### 影响面

- 所有 11 个 AI 工具的 admin 配置功能完全失效（产品级缺陷）
- siliconflow 等合规服务商调用直接崩溃（无法切厂商自救）

---

## 二、根因分析

### Bug-A：adapter 默认参数 + 13 个调用点漏传 provider

**adapter 函数签名**（`backend/app/adapters/yunwu.py`）：

```python
async def chat_stream(
    messages: list[dict],
    db: AsyncSession,
    model_id: str,
    provider: str = "yunwu",   # ← 默认参数是坑
    ...
):
```

**11 个 router 的 13 处 chat/chat_stream 调用都省略了 `provider=`**，落入默认值 `"yunwu"`，导致管理端配置的 siliconflow / glm 永不生效。

**漏传的 13 个调用点分布**：
- `operator_selling_point.py`（1 处 chat_stream）
- `operator_retrospective.py`（1 处）
- `operator_persona_writer.py`（3 处）
- `operator_seeding_writer.py`（5 处）
- `operator_values_writer.py`（4 处，含非流式 chat）
- `operator_qianchuan_writer.py`（1 处）
- `operator_qianchuan_preview.py`（1 处）
- `operator_tiktok_review.py`（1 处）
- `operator_benchmark.py`（1 处）
- `operator_livestream_writer.py`（1 处）
- `operator_tiktok_writer.py`（1 处，用 body.model，默认 yunwu）

### Bug-B：上游结尾帧 `choices:[]` 防御缺失

**位置**：`yunwu.py`
- L303（流式）：`chunk["choices"][0]` 当上游结尾帧返回 `choices:[]`（仅含 usage 统计）时 `[][0]` 抛 IndexError
- L179（非流式）：同款问题

**触发条件**：siliconflow 等服务商 SSE 流式响应在最后会发一个只含 usage 的帧（`choices: []`），yunwu 旧代码无脑取 `[0]` 直接崩。

---

## 三、修复方案

### 3.1 yunwu.py 防御空 choices

**L303 流式**：

```python
# 修前
delta = chunk["choices"][0].get("delta", {})

# 修后
choices = chunk.get("choices") or []
if not choices:
    continue   # 跳过 usage-only 结尾帧
delta = choices[0].get("delta", {})
```

**L179 非流式**：

```python
# 修前
content = data["choices"][0].get("message", {}).get("content", "")

# 修后
choices = data.get("choices") or []
if not choices:
    raise RuntimeError(
        f"chat failed [{provider}]: empty choices in response: {str(data)[:200]}"
    )
content = choices[0].get("message", {}).get("content", "")
```

### 3.2 11 个 router 加 `_resolve_model` helper

每个 router 加 2 个常量 + 1 个 helper：

```python
DEFAULT_MODEL = "claude-sonnet-4-6"   # 各 router 自定
DEFAULT_PROVIDER = "yunwu"


async def _resolve_model(config, db: AsyncSession) -> tuple[str, str]:
    """解析配置绑定的 (model_id, provider)，无绑定则返回默认值。"""
    if not config.ai_model_id:
        return DEFAULT_MODEL, DEFAULT_PROVIDER
    row = (await db.execute(
        text("SELECT model_id, COALESCE(provider, :default_p) FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id, "default_p": DEFAULT_PROVIDER},
    )).fetchone()
    return (row[0], row[1]) if row else (DEFAULT_MODEL, DEFAULT_PROVIDER)
```

调用点改成：

```python
# 修前
async for chunk in yunwu_adapter.chat_stream(messages=..., db=..., model_id=..., user_id=..., feature=..., max_tokens=...):

# 修后
model_id, provider = await _resolve_model(config, db)
async for chunk in yunwu_adapter.chat_stream(messages=..., db=..., model_id=model_id, provider=provider, user_id=..., feature=..., max_tokens=...):
```

### 3.3 后端开发约定 §4.2 写入红线

`backend/docs/后端开发约定.md` 加：

> §4.2 AI 调用必须显式传 `provider` 参数（多服务商切换）
> - `yunwu.chat()` / `yunwu.chat_stream()` 的 `provider` 是默认参数 `"yunwu"`
> - 调用方**必须**从 `ai_models` 表读 `(model_id, provider)` 二元组并显式传 `provider=provider`
> - ❌ 禁止省略 `provider=` 参数（即使默认 yunwu 也写出来）

---

## 四、涉及文件清单（17 个）

| # | 文件 | 类型 | 改动 |
|---|------|------|------|
| 1 | `backend/app/adapters/yunwu.py` | 代码 | L303 + L179 防御空 choices |
| 2 | `backend/app/routers/operator_selling_point.py` | 代码 | `_resolve_model` + provider 传递 |
| 3 | `backend/app/routers/operator_retrospective.py` | 代码 | 同上 |
| 4 | `backend/app/routers/operator_persona_writer.py` | 代码 | 同上（3 处调用） |
| 5 | `backend/app/routers/operator_seeding_writer.py` | 代码 | 同上（5 处调用） |
| 6 | `backend/app/routers/operator_values_writer.py` | 代码 | 同上（4 处含非流式 chat） |
| 7 | `backend/app/routers/operator_qianchuan_writer.py` | 代码 | 同上 |
| 8 | `backend/app/routers/operator_qianchuan_preview.py` | 代码 | 同上 |
| 9 | `backend/app/routers/operator_tiktok_review.py` | 代码 | 同上 |
| 10 | `backend/app/routers/operator_benchmark.py` | 代码 | 同上 |
| 11 | `backend/app/routers/operator_livestream_writer.py` | 代码 | 同上 |
| 12 | `backend/app/routers/operator_tiktok_writer.py` | 代码 | 同上（body.model 默认 yunwu） |
| 13 | `backend/tests/unit/services/test_yunwu_adapter.py` | 测试 | 新建：空 choices 防御 2 用例（流式 + 非流式） |
| 14 | `backend/tests/integration/routers/test_operator_selling_point.py` | 测试 | 加 provider 路由 2 用例 |
| 15 | `backend/docs/README.md` | 文档 | 「最近改动」段加本次 |
| 16 | `backend/docs/后端开发约定.md` | 文档 | §4.2 写入红线 |
| 17 | `docs/pm/PM_记忆与状态_M2.md` | PM | 加新工作项 |

**统计**：410 行新增 / 62 行删除，17 文件。

---

## 五、测试报告

### 5.1 后端单测

```bash
cd backend && source .venv311/Scripts/activate
pytest tests/unit/services/test_yunwu_adapter.py -v
pytest tests/integration/routers/test_operator_selling_point.py -v
```

| 用例 | 结果 |
|------|------|
| `test_yunwu_adapter.py::TestChatStream::test_skips_empty_choices_chunk` | ✅ |
| `test_yunwu_adapter.py::TestChat::test_raises_on_empty_choices_non_stream` | ✅ |
| `test_operator_selling_point.py::TestChat::test_chat_passes_default_provider_when_no_model` | ✅ |
| `test_operator_selling_point.py::TestChat::test_chat_passes_provider_from_ai_model` | ✅ |
| **新增小计** | **4/4 ✅** |

### 5.2 后端回归

```bash
pytest tests/ -v --ignore=tests/intake --ignore=tests/concurrent
```
**结果：253 个相关测试全过**（pre-existing 失败已排除）。

### 5.3 端到端真实验证

启动 dev 服，调 `POST /api/tools/selling-point-extractor/chat`：

```bash
curl -N -X POST http://localhost:8000/api/tools/selling-point-extractor/chat \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"产品 brief：..."}]}'
```
**结果**：默认 yunwu 配置流式输出正常，`ai_call_logs` 记录 `status=success`、`latency_ms≈8200`。

SQL 验证 `ai_models.provider` 字段可正确 JOIN 读取，`_pick_and_lock` 按 provider 过滤 `credentials` 工作正常。

---

## 六、红线合规检查

| # | 红线 | 合规 | 说明 |
|---|------|------|------|
| 1 | 非流式返回标准信封 | ✅ | 未改 |
| 2 | 写操作写 OperationLog | ✅ | 未改 |
| 3 | 前端走 request.ts | ✅ | 未改 |
| 4 | 改接口同步契约 | ✅ | 本次未改对外接口契约（adapter 内部参数变化，对外不变） |
| 5 | 改后端更新 README | ✅ | backend/docs/README.md 已加「最近改动」段 |
| 6 | AiCallLog 由 adapter 层写 | ✅ | 未改 |
| 7 | 新 router AsyncSessionLocal 注册 | ✅ | 本次未新增 router |
| 8 | 严禁物理删除 | ✅ | 未涉及 |
| 9 | 列表分页 | ✅ | 未涉及 |

---

## 七、验收签收

| 项 | 状态 |
|----|------|
| 后端单测 4/4 新增 | ✅ |
| 后端回归 253 相关全过 | ✅ |
| 端到端 curl：默认 yunwu 流式正常 | ✅ |
| 11 router 全部 `_resolve_model` 化 | ✅ |
| 后端开发约定 §4.2 红线写入 | ✅ |
| backend/docs/README.md 更新 | ✅ |
| PM 记忆更新 | ✅ |
| 任务单（本文件） | ✅（事后补） |
| PR #19 已合并 main | ✅（merge `a07c48b`） |

**PM 签收状态**：已合并 main，已签收。

---

## 八、回滚

纯代码改动，无 migration。`git revert ce1f7c1` 即可（但已合并 main 多日，回滚需评估下游影响）。

---

## 九、重要经验（已沉淀到 auto-memory）

`memory/ai_provider_default_arg.md` 已记录此坑：
- adapter 函数签名里 `provider` 是默认参数而非显式必传时，新调用点极易漏传
- 推荐范式：每个 router 抽 `_resolve_model(config, db) -> tuple[str, str]` helper
- ❌ 禁止省略 `provider=` 参数（即使默认 yunwu 也写出来）
- 后端开发约定 §4.2 已写入此红线

---

## 十、事后补写说明

**为什么本任务单是事后补写？**

PR #19 修复时按「最小化提交 + 快速验证」节奏走，直接 commit + 推 PR + 合并 main。事后 PM 复盘发现**任务单缺失**，违反 CLAUDE.md 功能完成链：

> 需求 → 任务(前/后端) → 代码 → 测试报告 → 验收 → 更新 README → 更新 PM 记忆 → **签收**

任务单是其中第二环。本次事后补写时点：2026-07-03 同日稍晚（在补 BugFix-04 任务单时发现 PR #19 也漏了）。

**教训**：bug 修复虽小，仍要走完整链路。后续修复（无论大小）一律先写任务单再改代码。

---

## 十一、关联文档

- **同日稍晚补修补**：`backend/docs/tasks/BugFix-04_qianchuan-edit-review_provider切换无效.md`（PR #19 漏掉的 `tool_chat_stream.py` 共享 router）
- **PR commit**：`ce1f7c1a02e6d1f3dec01bcd58db2d82b00338da`
- **Merge commit**：`a07c48b`
- **auto-memory**：`memory/ai_provider_default_arg.md`
- **后端开发约定**：§4.2
