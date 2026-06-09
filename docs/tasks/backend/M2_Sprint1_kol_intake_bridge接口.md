# 后端任务单 · kol-intake bridge 接口

> 目标：新增两个接口，将对话逻辑从「AI主导」改为「前端主导」：
> 1. `GET /api/intake/questions` — 返回题目列表（前端用来驱动对话流程）
> 2. `POST /api/intake/{token}/bridge` — AI 只生成过渡语，不改写题目文本
>
> 现有 `/api/intake/{token}/chat` 接口保留不动（运营直发场景仍使用）。
>
> 涉及文件：
> - 修改 `backend/app/routers/intake_public.py`（新增两个接口）

---

## 背景说明

旧架构对话逻辑：
- 前端管理题目列表和当前题目索引
- 用户回答后，前端调 bridge，传入「用户回答 + 当前题文本 + 下一题文本」
- AI 只生成 1-2 句过渡语（回应用户答案 + 自然引出下一题）
- 题目原文由前端直接显示，不经过 AI 处理

新增接口完全复刻这个逻辑。

---

## 接口 1 — GET /api/intake/questions

**无需鉴权**（题目列表是公开配置）

返回所有启用的题目，供前端驱动对话流程：

```python
@router.get("/questions")
async def get_questions(db: AsyncSession = Depends(get_db)):
    questions = (await db.execute(
        select(KolIntakeQuestion)
        .where(KolIntakeQuestion.is_active == True)
        .order_by(KolIntakeQuestion.order_num)
    )).scalars().all()

    return success_response(data=[
        {
            "id":            q.id,
            "order_num":     q.order_num,
            "category":      q.category,
            "question_text": q.question_text,
            "question_type": q.question_type,   # "text" | "multi_collect"
            "max_items":     q.max_items,
            "is_required":   q.is_required,
        }
        for q in questions
    ])
```

---

## 接口 2 — POST /api/intake/{token}/bridge

**无需鉴权**（与现有 chat 接口一致）

AI 只生成过渡语，使用 `claude-haiku-4-5`（轻量快速），不管理题目流程。

### 请求体

```python
class BridgeRequest(BaseModel):
    user_answer: str
    question_text: str                  # 当前题目原文
    next_question_text: str | None = None   # 下一题原文（最后一题时为 None）
    next_question_hint: str | None = None   # 下一题提示（可选）
    is_last_question: bool = False
    is_section_change: bool = False
    next_section: str | None = None
    is_multi_collect: bool = False      # 是否 multi_collect 题型
    collect_count: int = 0              # 当前已收集条数
```

### 实现

```python
@router.post("/{token}/bridge")
async def intake_bridge(
    token: str,
    body: BridgeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI 过渡语接口。
    - 仅生成对用户回答的回应 + 自然引出下一题的过渡语
    - 题目原文由前端直接显示，不经过 AI 处理
    - 固定使用 claude-haiku-4-5，max_tokens=200
    """
    await _get_valid_link(token, db)  # 校验链接有效性

    # 构建 instruction（与旧架构 bridge/route.ts 逻辑一致）
    if body.is_multi_collect and body.collect_count > 0:
        instruction = (
            f'用户正在回答一个可以填多条的问题："{body.question_text}"，'
            f'这是他们的第 {body.collect_count} 条回答。\n'
            '请先对这条回答做出真诚的回应（共情、好奇、肯定都可以，要具体到他们说的内容），'
            '然后自然地问他们还有没有其他的。\n'
            '不要说"记下了"这种机械的话。像朋友聊天一样。'
        )
    elif body.is_last_question:
        instruction = (
            f'用户刚回答了最后一道问题："{body.question_text}"。\n'
            '请对回答做出真诚的回应，然后用温暖自然的方式告诉他们所有问题都聊完了，'
            '辛苦了，可以点击提交生成报告了。'
        )
    else:
        section_note = (
            f'\n下一个版块是「{body.next_section}」，简单过渡一下。'
            if body.is_section_change and body.next_section else ''
        )
        hint_note = (
            f'\n提示信息（帮你理解这个问题想问什么，但不要直接念出来）：{body.next_question_hint}'
            if body.next_question_hint else ''
        )
        instruction = (
            f'用户刚回答了问题："{body.question_text}"。\n'
            '请先对回答做出真诚的回应（1-2句，要具体到他们说的内容，不要泛泛而谈），'
            f'然后自然地过渡到下一个话题。{section_note}\n'
            '最后，用一句自然的话引出下一题即可，不要把下一题的题目文本念出来，'
            '前端会直接显示题目原文。'
            f'\n下一个问题是："{body.next_question_text}"{hint_note}'
        )

    system_prompt = (
        '你是一个红人孵化团队的面试官，正在和一个新红人聊天了解他/她的情况。\n'
        '你的风格：温暖、真诚、有洞察力，像一个聊得来的朋友。\n'
        '- 回应要具体到用户说的内容，不要用万能回复\n'
        '- 语气自然口语化，不要太正式\n'
        '- 简洁，整体不超过2句话\n'
        '- 不要用"好的""收到""了解"这种客服话术开头\n'
        '- 不要重复或改写题目文本，题目由系统直接展示给用户\n'
        '- 不要用emoji'
    )

    # 固定用 haiku，不走 credential_selector，直接读 conversation_bridge 配置的 credential
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

    try:
        reply = await yunwu_adapter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f'{instruction}\n\n用户的回答是：\n"{body.user_answer}"'},
            ],
            db=db,
            model_id=ai_model.model_id,
            provider=ai_model.provider,
            feature="kol_intake_bridge",
            max_tokens=200,
            temperature=0.7,
        )
    except Exception:
        reply = ""  # bridge 失败静默降级，前端直接显示题目原文

    return success_response(data={"reply": reply})
```

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `intake_public.py` | 新增 `GET /api/intake/questions` |
| 2 | `intake_public.py` | 新增 `POST /api/intake/{token}/bridge` |

**改动量**：约 80 行净增，现有接口零改动。

---

## 完成后验证

```bash
# 获取题目列表
GET /api/intake/questions
# 预期：返回 24 道题的数组，含 question_text / question_type / is_required 等字段

# bridge 过渡语
POST /api/intake/{valid_token}/bridge
{
  "user_answer": "我叫小花",
  "question_text": "你希望粉丝怎么叫你？",
  "next_question_text": "你的抖音账号名叫什么？",
  "is_last_question": false,
  "is_section_change": false
}
# 预期：{ reply: "小花这个名字很亲切！那你的抖音账号名是什么呢？" }
# 注意：reply 不包含题目原文，只是过渡语
```
