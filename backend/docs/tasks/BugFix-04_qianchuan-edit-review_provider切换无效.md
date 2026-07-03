# MCN_PM_Agent — BugFix-04 任务与验收（qianchuan-edit-review provider 切换无效 + admin 配模型无效）

> 角色：MCN_PM_Agent（PM + 跨端开发）
> 工作目录：`backend/` + `frontend/`
> PM 生成时间：2026-07-03
> 完成时间：2026-07-03（同日完成）
> 优先级：P1（admin 配置不生效，影响用户在服务器部署）
> 关联：补修补 PR #19（同日稍早修复 13 个 operator_* router 同款坑，本次补漏）
> 状态：**已完成**（待 commit + 推 PR + 部署）

---

## 一、Bug 描述

**现象 1**：admin 在「工具配置 → 千川剪辑预审」选 siliconflow 模型并保存后，运营端调用预审仍走 yunwu（用户服务器上 yunwu 503 时切 siliconflow 不生效）。

**现象 2**：admin 配的 `ai_model_id` 在 `QianChuanEditReviewPage` 拿到后完全没用，`analyze()` 仍硬编码 `'gpt-4o'`。**配置选了等于白选**。

**影响**：
- 服务器 yunwu 503 时无法通过切厂商自救
- admin 配模型功能对本工具完全无效（产品级缺陷）

---

## 二、根因分析

### Bug-1：`tool_chat_stream.py` 漏传 `provider=`

**文件**：`backend/app/routers/tool_chat_stream.py`（修前 81 行）

**问题**：第 59-66 行调 `yunwu_adapter.chat_stream(...)` 时**没有传 `provider=` 参数**，落入 `yunwu.py:228` 的默认参数 `provider: str = "yunwu"`。

**与 PR #19 的关系**：同日稍早 PR #19 修过 13 个 `operator_*` router 同款坑。但当时 grep 范围只覆盖 `operator_*` 系列，**漏掉了 `tool_*` 系列里的共享 router** `tool_chat_stream.py`。`POST /api/tools/chat-stream` 当前只有 qianchuan-edit-review 一个前端调用方，但仍属"共享 router"，不能硬绑 config 表。

### Bug-2：前端硬编码 model + 后端不接受 ai_model_id

**文件链路**：
- `frontend/src/pages/operator/QianChuanEditReviewPage.tsx:163`：`chatStream(..., 'gpt-4o', 8000)` 硬编码
- `frontend/src/api/qianchuanEditReview.ts:79-93`：`chatStream` 函数体只接受 `model` 字符串
- `backend/app/routers/tool_chat_stream.py`（修前）：`ChatStreamRequest` 无 `ai_model_id` 字段

**问题**：`QianChuanEditReviewPage.useEffect` 已能从 `getConfig()` 拉到 `ai_model_id`，但只用来覆盖 system_prompt（line 95-97 的 `if (cfg.system_prompt)`），**完全没用 ai_model_id**。

---

## 三、修复方案

### 关键设计决策

**共享 router 不能硬绑特定工具的 config 表**。正确做法：
- 前端把 `ai_model_id` 放到 chat-stream 的 JSON body
- 后端按需查 `ai_models` 表解析 `(model_id, provider)`
- 不传 `ai_model_id` 时回退默认值（向后兼容）

参照 `operator_selling_point.py:77-85` 的 `_resolve_model`，但**改为接受 `int | None` 而非 config 对象**——保留共享 router 的通用性。

### 后端改动

#### 1. `backend/app/routers/tool_chat_stream.py`

```python
from sqlalchemy import text

DEFAULT_MODEL = "gpt-4o"
DEFAULT_PROVIDER = "yunwu"


async def _resolve_model(ai_model_id: int | None, db: AsyncSession) -> tuple[str, str]:
    """解析 ai_model_id → (model_id, provider)；无值或失效则返回默认。"""
    if not ai_model_id:
        return DEFAULT_MODEL, DEFAULT_PROVIDER
    row = (await db.execute(
        text(
            "SELECT model_id, COALESCE(provider, :default_p) "
            "FROM ai_models WHERE id = :id AND status = 'active'"
        ),
        {"id": ai_model_id, "default_p": DEFAULT_PROVIDER},
    )).fetchone()
    return (row[0], row[1]) if row else (DEFAULT_MODEL, DEFAULT_PROVIDER)


class ChatStreamRequest(BaseModel):
    messages: list[dict]
    system_prompt: str
    model: str = "gpt-4o"
    max_tokens: int = 8000
    ai_model_id: int | None = None  # 🆕


@router.post("/chat-stream")
async def chat_stream(
    body: ChatStreamRequest,
    db: AsyncSession = Depends(get_db),   # 🆕 用于解析 ai_model_id
    current_user: User = Depends(require_password_changed),
):
    ...
    model_id, provider = await _resolve_model(body.ai_model_id, db)
    ...
    # generate() 内 yunwu_adapter.chat_stream(...) 显式传 provider=provider
```

#### 2. `backend/tests/integration/routers/test_tool_chat_stream.py`

- 原 `fake_stream(messages, db, model_id, user_id, feature, max_tokens, **kwargs)` 加 `**kwargs` 兼容
- 加 2 用例：
  - `test_passes_default_provider_when_no_ai_model_id`：不传 ai_model_id → provider="yunwu"
  - `test_passes_provider_from_ai_model_id`：INSERT siliconflow ai_model + 传 ai_model_id → provider="siliconflow"，model_id 来自 DB

### 前端改动

#### 3. `frontend/src/api/qianchuanEditReview.ts`

```typescript
export function chatStream(
  messages: Array<{ role: string; content: unknown }>,
  systemPrompt: string,
  model = 'gpt-4o',
  maxTokens = 8000,
  aiModelId?: number | null,   // 🆕
): Promise<Response> {
  return fetch('/api/tools/chat-stream', {
    ...
    body: JSON.stringify({
      messages, system_prompt: systemPrompt, model, max_tokens: maxTokens,
      ...(aiModelId ? { ai_model_id: aiModelId } : {}),   // 🆕 仅非空时传
    }),
  })
}
```

#### 4. `frontend/src/pages/operator/QianChuanEditReviewPage.tsx`

```typescript
const [activeModelId, setActiveModelId] = useState<number | null>(null)  // 🆕

useEffect(() => {
  getConfig().then(cfg => {
    if (cfg.system_prompt) setActivePrompt(cfg.system_prompt)
    if (cfg.ai_model_id) setActiveModelId(cfg.ai_model_id)   // 🆕
  }).catch(() => {/* ... */})
}, [])

// analyze() 内
const resp = await chatStream(
  [{ role: 'user', content: buildMessage() }],
  activePrompt,
  'gpt-4o',
  8000,
  activeModelId,   // 🆕 有值则后端用 DB 的 model_id 覆盖
)
```

---

## 四、涉及文件清单

| # | 文件 | 类型 | 改动 |
|---|------|------|------|
| 1 | `backend/app/routers/tool_chat_stream.py` | 代码 | 加 `_resolve_model` + `ai_model_id` 字段 + `provider=` 传递 |
| 2 | `backend/tests/integration/routers/test_tool_chat_stream.py` | 测试 | 加 2 用例 + `**kwargs` 兼容 |
| 3 | `frontend/src/api/qianchuanEditReview.ts` | 代码 | `chatStream` 加 `aiModelId` 参数 |
| 4 | `frontend/src/pages/operator/QianChuanEditReviewPage.tsx` | 代码 | 加 `activeModelId` state + 传参 |
| 5 | `backend/docs/base/MCN_M2_Base_API.md` | 文档 | §chat-stream 加 `ai_model_id` 字段说明 |
| 6 | `backend/docs/README.md` | 文档 | 「最近改动」段加补修补条目 |
| 7 | `frontend/docs/README.md` | 文档 | qianchuanEditReview 行加注 |
| 8 | `docs/pm/PM_记忆与状态_M2.md` | PM | 加新工作项 + 顶部时间戳 |
| 9 | auto-memory `ai_provider_default_arg.md` | PM | 追加 grep 范围教训 |

---

## 五、测试报告

### 5.1 后端单测

```bash
cd backend && source .venv311/Scripts/activate
pytest tests/integration/routers/test_tool_chat_stream.py -v --no-cov
```

| 用例 | 结果 |
|------|------|
| TestAuth::test_unauthorized | ✅ |
| TestChatStream::test_system_prompt_prepended | ✅ |
| TestChatStream::test_empty_messages_returns_400 | ✅ |
| TestChatStream::test_empty_system_prompt_returns_400 | ✅ |
| TestChatStream::test_passes_default_provider_when_no_ai_model_id（**新**） | ✅ |
| TestChatStream::test_passes_provider_from_ai_model_id（**新**） | ✅ |
| **合计** | **6/6 ✅** |

### 5.2 后端相关测试回归

```bash
pytest tests/integration/routers/test_tool_qianchuan_edit_review.py \
       tests/integration/routers/test_tool_chat_stream.py \
       tests/integration/routers/test_tool_export_word.py \
       tests/integration/routers/test_tool_transcribe.py -v --no-cov
```
**结果：19/19 ✅**

### 5.3 前端类型检查

```bash
cd frontend && npx tsc --noEmit
```
**结果：0 错误**

### 5.4 端到端真实验证

启动临时 dev 服（8050 端口，.venv311 环境），调 `POST /api/tools/chat-stream` 传 `ai_model_id=3`（DB id=3 = siliconflow / Qwen/Qwen3-Omni-30B-A3B-Thinking）：

```bash
curl -N -X POST http://localhost:8050/api/tools/chat-stream \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好，简短回复"}],
       "system_prompt":"你是测试助手，回复不超过20字",
       "model":"gpt-4o","max_tokens":100,"ai_model_id":3}'
# HTTP 200，响应："\n\n你好。"
```

查 `ai_call_logs` 最新一条（id=180）：

| 字段 | 期望值 | 实际值 | 通过 |
|------|--------|--------|------|
| feature | `qianchuan_edit_review_chat` | `qianchuan_edit_review_chat` | ✅ |
| model_id | `Qwen/Qwen3-Omni-30B-A3B-Thinking` | `Qwen/Qwen3-Omni-30B-A3B-Thinking` | ✅（DB 覆盖了 body.model='gpt-4o'） |
| credential_id | `6`（siliconflow 凭证） | `6` | ✅（不是 yunwu 的 credential_id=1） |
| status | `success` | `success` | ✅ |

**结论：siliconflow 真实切换生效** ✅

---

## 六、红线合规检查

| # | 红线 | 合规 | 说明 |
|---|------|------|------|
| 1 | 非流式返回标准信封 | ✅ | chat-stream 是流式例外（StreamingResponse text/plain），不改 |
| 2 | 写操作写 OperationLog | ✅ | 本次不涉及 POST 写操作（chat-stream 是只读流式） |
| 3 | 前端走 request.ts | ✅ | chatStream 是 SSE 流式例外（裸 fetch + getReader），合规 |
| 4 | 改接口同步契约 | ✅ | Base_API §chat-stream 已更新 |
| 5 | 改后端/前端更新 README | ✅ | 双 README 均已更新 |
| 6 | AiCallLog 由 adapter 层写 | ✅ | yunwu.py 的 finally 块写，router 不重复 |
| 7 | 新 router AsyncSessionLocal 注册 | ✅ | 已注册（Sprint07）；本次新加的 `get_db` 全局 patch |
| 8 | 严禁物理删除 | ✅ | 本次不涉及删除 |
| 9 | 列表分页 | ✅ | 本次不涉及列表 |

---

## 七、验收签收

| 项 | 状态 |
|----|------|
| 后端单测 6/6 | ✅ |
| 后端相关回归 19/19 | ✅ |
| 前端 tsc 0 错误 | ✅ |
| 端到端 curl：siliconflow 切换生效 | ✅ |
| Base_API 契约更新 | ✅ |
| 双 README 更新 | ✅ |
| PM 记忆更新 | ✅ |
| auto-memory 教训追加 | ✅ |
| 任务单（本文件） | ✅ |

**PM 签收状态**：待用户确认 + commit + 推 PR + 部署。

---

## 八、回滚

纯代码改动，无 migration。`git revert` 即可。

---

## 九、重要经验（写入 auto-memory）

「同款 pattern 修复」必须列出**全部调用方清单**核对。PR #19 当时只 grep `operator_*` 系列，漏掉了 `tool_*` 系列里的共享 router。**后续修复同类"调用方漏传参数"问题时，grep 范围必须覆盖 `app/routers/` 全部**，不能按命名前缀过滤。
