# 后端任务单 · kol-intake bridge 接口优化

> 问题：
> 1. bridge 返回的过渡语用问句结尾，导致用户看到「AI问题 + 题目原文」两个问题
> 2. bridge 的 system_prompt 硬编码在代码里，管理后台「对话Prompt」对 bridge 无效
>
> 涉及文件：
> - `backend/app/routers/intake_public.py`
> - `backend/app/routers/operator_intake_direct.py`

---

## 改动 1 — instruction 禁止用问句结尾（两个文件都改）

**问题根因**：instruction 写的是「用一句自然的话引出下一题」，AI 把「引出」理解成用问句带出，
导致过渡语本身就是一个问题，加上前端紧接着显示题目原文，用户看到两个问题。

### intake_public.py（第 252-254 行）

```python
# 改前
instruction = (
    f'用户刚回答了问题："{body.question_text}"。\n'
    '请先对回答做出真诚的回应（1-2句，要具体到他们说的内容，不要泛泛而谈），'
    f'然后自然地过渡到下一个话题。{section_note}\n'
    '最后，用一句自然的话引出下一题即可，不要把下一题的题目文本念出来，'
    '前端会直接显示题目原文。'
    f'\n下一个问题是："{body.next_question_text}"{hint_note}'
)

# 改后
instruction = (
    f'用户刚回答了问题："{body.question_text}"。\n'
    '请先对回答做出真诚的回应（1-2句，要具体到他们说的内容，不要泛泛而谈），'
    f'然后自然地过渡到下一个话题。{section_note}\n'
    '最后用一句简短的陈述句收尾即可（例如"我们再聊聊下一个方向"），'
    '绝对不能用问句结尾，不能自己造问题，题目由系统直接展示给用户。'
    f'\n下一个问题是："{body.next_question_text}"{hint_note}'
)
```

### operator_intake_direct.py（同样位置，同样修改）

找到 bridge 接口中相同的 instruction 构建逻辑，做完全一致的修改。

---

## 改动 2 — system_prompt 从数据库读取（两个文件都改）

**目标**：管理后台修改「对话Prompt」后，bridge 接口立即生效，无需改代码。

### 当前逻辑（两个文件都是这样）

```python
# 硬编码 system_prompt
system_prompt = (
    '你是一个红人孵化团队的面试官...\n'
    '- 回应要具体到用户说的内容...\n'
    ...
)

# 然后读取 config 只是为了拿模型
config = (await db.execute(
    select(KolIntakeConfig).where(KolIntakeConfig.config_key == "conversation_bridge")
)).scalar_one_or_none()
```

### 改后逻辑

```python
# 读取 conversation_bridge 配置（模型 + system_prompt 都从这里取）
config = (await db.execute(
    select(KolIntakeConfig).where(KolIntakeConfig.config_key == "conversation_bridge")
)).scalar_one_or_none()

if config is None or config.ai_model_id is None:
    return success_response(data={"reply": ""})

ai_model = (await db.execute(
    select(AiModel).where(AiModel.id == config.ai_model_id)
)).scalar_one_or_none()

if ai_model is None:
    return success_response(data={"reply": ""})

# system_prompt：优先用数据库配置，fallback 用默认值
DEFAULT_BRIDGE_SYSTEM_PROMPT = (
    '你是一个红人孵化团队的面试官，正在和一个新红人聊天了解他/她的情况。\n'
    '你的风格：温暖、真诚、有洞察力，像一个聊得来的朋友。\n'
    '- 回应要具体到用户说的内容，不要用万能回复\n'
    '- 语气自然口语化，不要太正式\n'
    '- 简洁，整体不超过2句话\n'
    '- 不要用"好的""收到""了解"这种客服话术开头\n'
    '- 不要重复或改写题目文本，题目由系统直接展示给用户\n'
    '- 用陈述句收尾，不要用问句结尾，不要自己造问题\n'
    '- 不要用emoji'
)

system_prompt = config.system_prompt or DEFAULT_BRIDGE_SYSTEM_PROMPT
```

**注意**：
- 读取 config 的代码块移到 instruction 构建之前（原来在后面）
- `DEFAULT_BRIDGE_SYSTEM_PROMPT` 新增了一条「用陈述句收尾，不要用问句结尾，不要自己造问题」
- 两个文件（intake_public.py 和 operator_intake_direct.py）做完全一致的修改

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `intake_public.py` | instruction 改为陈述句收尾 |
| 2 | `intake_public.py` | system_prompt 从 DB 读取，fallback 默认值 |
| 3 | `operator_intake_direct.py` | 同上两项 |

**改动量**：约 20 行，重启后端生效。

---

## 验证

| 验证点 | 预期 |
|--------|------|
| 回答问题后 AI 过渡语 | 只有 1-2 句回应 + 陈述句收尾，不出现问号结尾 |
| 用户看到的内容 | AI 过渡语（陈述句）→ 题目原文，只有一个问题 |
| 管理后台修改「对话Prompt」| bridge 接口立即使用新 Prompt，无需重启 |
| 未配置 Prompt 时 | 使用 DEFAULT_BRIDGE_SYSTEM_PROMPT，正常工作 |
