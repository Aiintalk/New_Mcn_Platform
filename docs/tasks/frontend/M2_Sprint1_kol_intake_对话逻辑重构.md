# 前端任务单 · kol-intake 对话逻辑重构（前端驱动）

> 目标：将 IntakePage 和 OperatorIntakeChatPage 的对话逻辑从「AI 主导」改为「前端主导」，
> 复刻旧架构的对话模式：题目原文由前端直接显示，AI 只生成过渡语。
>
> 涉及文件：
> - `src/api/intake.ts`（新增两个 API 函数）
> - `src/types/intake.ts`（新增 IntakeQuestion 类型）
> - `src/pages/intake/IntakePage.tsx`（核心逻辑重构）
> - `src/pages/operator/OperatorIntakeChatPage.tsx`（同步重构）

---

## 旧架构逻辑说明（实现参考）

```
1. 页面挂载时：GET /api/intake/questions 获取题目列表
2. 显示开场白（固定文案，不调 AI）
3. 用户点「开始」→ 显示第 0 题原文 + hint
4. 用户输入回答 → 发送
5. 调 POST /bridge（传：用户回答 + 当前题文本 + 下一题文本）
6. AI 返回过渡语（1-2句） → 前端显示
7. 前端直接显示下一题原文（不经过 AI）
8. 重复 4-7 直到最后一题
9. 最后一题回答后，AI 返回收尾语 → 显示「提交」按钮
```

multi_collect 题型特殊处理：
- 同一道题循环收集，每次收集后调 bridge（传 collect_count）
- 用户输入「没了」/「没有」等结束词 → 结束收集，进入下一题
- 达到 max_items 上限 → 自动结束收集

---

## 改动 1 — 新增类型

**文件**：`src/types/intake.ts`

```ts
export interface IntakeQuestion {
  id: number;
  order_num: number;
  category: string;
  question_text: string;
  question_type: 'text' | 'multi_collect';
  max_items: number | null;
  is_required: boolean;
}
```

---

## 改动 2 — 新增 API 函数

**文件**：`src/api/intake.ts`

```ts
// 获取题目列表（无需 token）
export const getIntakeQuestions = () =>
  get<IntakeQuestion[]>('/api/intake/questions');

// bridge 过渡语
export const bridgeIntake = (token: string, data: {
  user_answer: string;
  question_text: string;
  next_question_text?: string;
  next_question_hint?: string;
  is_last_question?: boolean;
  is_section_change?: boolean;
  next_section?: string;
  is_multi_collect?: boolean;
  collect_count?: number;
}) => post<{ reply: string }>(`/api/intake/${token}/bridge`, data);
```

---

## 改动 3 — IntakePage 核心逻辑重构

**文件**：`src/pages/intake/IntakePage.tsx`

### 3.1 新增 state

```tsx
const [questions, setQuestions] = useState<IntakeQuestion[]>([]);
const [currentQIdx, setCurrentQIdx] = useState(-1);   // -1 = 未开始
const [collectCount, setCollectCount] = useState(0);  // multi_collect 已收集条数
const [collectItems, setCollectItems] = useState<string[]>([]);
const [done, setDone] = useState(false);  // 所有题目已回答完
```

### 3.2 页面挂载：先获取题目列表

在原有 `getIntakeInfo` 调用前，先加载题目列表：

```tsx
useEffect(() => {
  if (!token) { setPhase('error'); setErrMsg('无效链接'); return; }

  // 并行加载：题目列表 + 链接信息
  Promise.all([
    getIntakeQuestions(),
    getIntakeInfo(token),
  ]).then(([qs, info]) => {
    setQuestions(qs);
    setKolName(info.kol_name);

    if (info.already_submitted) {
      if (info.existing_messages?.length) setMessages(info.existing_messages);
      setPhase('submitted');
      pollStatus();
    } else {
      const existing = info.existing_messages ?? [];
      setMessages(existing);
      setPhase('chat');
      // 有历史消息则恢复进度，否则显示开场白
      if (existing.length === 0) showWelcome();
    }
  }).catch(err => {
    const code = (err as { code?: string }).code;
    if (code === 'LINK_EXPIRED') { setPhase('expired'); return; }
    setPhase('error');
    setErrMsg((err as Error).message || '链接无效');
  });
// eslint-disable-next-line react-hooks/exhaustive-deps
}, [token]);
```

### 3.3 开场白（不调 AI，固定文案）

```tsx
function showWelcome() {
  const welcomeMsg: ChatMessage = {
    role: 'assistant',
    content: '你好呀！我是团队里专门负责了解新伙伴的，接下来我们就轻松聊聊，我想听听你的故事和想法，这样团队才能更懂你，帮你找到最适合你的内容方向。\n\n不用紧张，就当跟朋友聊天就好，大概十来分钟。有些问题如果不想答可以跳过。准备好了就点下面的按钮～',
    ts: new Date().toISOString(),
  };
  setMessages([welcomeMsg]);
  // currentQIdx 保持 -1，等用户点「开始」
}
```

### 3.4 开始按钮

当 `currentQIdx === -1 && !done` 时，输入区显示「开始聊吧」按钮（替代输入框）：

```tsx
function handleStart() {
  if (questions.length === 0) return;
  const firstQ = questions[0];
  // 显示第一题
  showQuestion(0);
}

function showQuestion(idx: number) {
  const q = questions[idx];
  setCurrentQIdx(idx);
  setCollectCount(0);
  setCollectItems([]);

  // 直接在消息流里显示题目原文
  const qMsg: ChatMessage = {
    role: 'assistant',
    content: buildQuestionText(q, idx),
    ts: new Date().toISOString(),
  };
  setMessages(prev => [...prev, qMsg]);
}

function buildQuestionText(q: IntakeQuestion, idx: number): string {
  const reqNote = q.is_required ? '' : '（选填，可输入"跳过"）';
  const hint = '';  // hint 单独作为一条消息显示
  return `${q.question_text} ${reqNote}`.trim();
}
```

如果题目有 hint（后端暂无 hint 字段，可在 question_text 后展示，或后期后端加 hint 字段）。

### 3.5 用户发送回答

```tsx
// 结束词判断（multi_collect 用）
const DONE_KEYWORDS = ['没了', '没有了', '就这些', '没有', '没', '无', '就这样', 'no', '算了'];
function isDoneKeyword(val: string) {
  return DONE_KEYWORDS.includes(val.trim().toLowerCase());
}

async function handleSend() {
  if (!input.trim() || !token || sending || currentQIdx < 0) return;
  const val = input.trim();
  const q = questions[currentQIdx];
  const isSkip = val === '跳过' || val === '跳';

  // 必填题不允许跳过
  if (q.is_required && isSkip) {
    const tipMsg: ChatMessage = { role: 'assistant', content: '这道题挺重要的，尽量填一下吧～', ts: new Date().toISOString() };
    setMessages(prev => [...prev, tipMsg]);
    return;
  }

  // 追加用户消息
  const userMsg: ChatMessage = { role: 'user', content: val, ts: new Date().toISOString() };
  setMessages(prev => [...prev, userMsg]);
  setInput('');
  setSending(true);

  try {
    if (q.question_type === 'multi_collect' && !isSkip) {
      await handleMultiCollect(val, q);
    } else {
      await handleNormalAnswer(val, q, isSkip);
    }
  } finally {
    setSending(false);
  }
}
```

### 3.6 普通题目处理

```tsx
async function handleNormalAnswer(val: string, q: IntakeQuestion, isSkip: boolean) {
  const nextIdx = currentQIdx + 1;
  const isLast = nextIdx >= questions.length;
  const nextQ = isLast ? null : questions[nextIdx];

  // 调 bridge 获取过渡语
  const bridgeRes = await bridgeIntake(token!, {
    user_answer: isSkip ? '（跳过）' : val,
    question_text: q.question_text,
    next_question_text: nextQ?.question_text,
    is_last_question: isLast,
    is_section_change: nextQ ? nextQ.category !== q.category : false,
    next_section: nextQ?.category,
  }).catch(() => ({ reply: '' }));

  // 显示 AI 过渡语（如果有）
  if (bridgeRes.reply) {
    setMessages(prev => [...prev, {
      role: 'assistant', content: bridgeRes.reply, ts: new Date().toISOString(),
    }]);
  }

  if (isLast) {
    setDone(true);
    return;
  }

  // 直接显示下一题原文
  showQuestion(nextIdx);
}
```

### 3.7 multi_collect 题目处理

```tsx
async function handleMultiCollect(val: string, q: IntakeQuestion) {
  const isDone = isDoneKeyword(val);

  // 第一条就说没了，必填题不允许
  if (isDone && collectCount === 0 && q.is_required) {
    setMessages(prev => [...prev, {
      role: 'assistant', content: '这道题挺重要的，至少说一个吧～', ts: new Date().toISOString(),
    }]);
    setSending(false);
    return;
  }

  if (isDone || collectCount + 1 >= (q.max_items ?? 3)) {
    // 收集结束，进入下一题
    setCollectCount(0);
    setCollectItems([]);
    await handleNormalAnswer(val, q, false);
    return;
  }

  // 继续收集
  const newCount = collectCount + 1;
  setCollectCount(newCount);
  setCollectItems(prev => [...prev, val]);

  // 调 bridge 询问是否还有更多
  const bridgeRes = await bridgeIntake(token!, {
    user_answer: val,
    question_text: q.question_text,
    is_multi_collect: true,
    collect_count: newCount,
  }).catch(() => ({ reply: '' }));

  const reply = bridgeRes.reply || '还有没有其他的？没有的话输入"没了"就行。';
  setMessages(prev => [...prev, {
    role: 'assistant', content: reply, ts: new Date().toISOString(),
  }]);
}
```

### 3.8 输入区 UI 逻辑

```tsx
// 输入区根据状态显示不同内容
{currentQIdx === -1 && !done ? (
  // 开始按钮
  <button className="btn btn-primary" style={{ width: '100%', padding: '12px' }}
    onClick={handleStart}>
    开始聊吧 →
  </button>
) : done ? (
  // 提交按钮
  <button className="btn btn-primary" style={{ width: '100%', padding: '12px' }}
    onClick={handleSubmit} disabled={submitting}>
    {submitting ? '提交中…' : '提交并生成报告 →'}
  </button>
) : (
  // 正常输入框（原有样式保留）
  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
    <textarea ... />
    <button ... />  {/* 发送按钮 */}
  </div>
)}
```

### 3.9 handleSubmit 调整

不再需要检查消息条数（前端已控制答完所有必填题才显示提交按钮），直接提交：

```tsx
async function handleSubmit() {
  if (!token || !done) return;
  setSubmitting(true);
  try {
    await submitIntake(token, messages);
    setPhase('submitted');
    pollStatus();
  } catch (err: unknown) {
    message.error((err as Error).message || '提交失败，请重试');
  } finally {
    setSubmitting(false);
  }
}
```

---

## 改动 4 — OperatorIntakeChatPage 同步重构

**文件**：`src/pages/operator/OperatorIntakeChatPage.tsx`

逻辑与 IntakePage 完全一致，差异：
- 获取题目列表：`getIntakeQuestions()`（同 IntakePage）
- bridge 接口：新增 `bridgeOperatorDirect` 到 `src/api/intakeDirect.ts`

```ts
// 新增到 intakeDirect.ts
export const bridgeOperatorDirect = (sessionId: number, data: {
  user_answer: string;
  question_text: string;
  next_question_text?: string;
  is_last_question?: boolean;
  is_section_change?: boolean;
  next_section?: string;
  is_multi_collect?: boolean;
  collect_count?: number;
}) => post<{ reply: string }>(`/api/operator/intake/direct/${sessionId}/bridge`, data);
```

> **注意**：运营直发 bridge 接口需要后端同步新增
> `POST /api/operator/intake/direct/{session_id}/bridge`
> 逻辑与 `/api/intake/{token}/bridge` 完全一致，只是鉴权方式不同（JWT vs token）。
> 后端已有 `operator_intake_direct.py`，在此文件中新增该接口即可。

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `types/intake.ts` | 新增 `IntakeQuestion` 类型 |
| 2 | `api/intake.ts` | 新增 `getIntakeQuestions` / `bridgeIntake` |
| 3 | `api/intakeDirect.ts` | 新增 `bridgeOperatorDirect` |
| 4 | `IntakePage.tsx` | 逻辑重构：前端驱动题目流程，AI 只生成过渡语 |
| 5 | `OperatorIntakeChatPage.tsx` | 同步重构 |

**改动量**：约 150 行净改，TypeScript 零新 `any`，零新依赖。

---

## 完成后验证

| 验证点 | 预期 |
|--------|------|
| 打开对话页 | 显示固定开场白，底部显示「开始聊吧」按钮 |
| 点击「开始聊吧」| 显示第 1 题原文「你希望粉丝怎么叫你？」 |
| 回答第 1 题 | AI 显示 1-2 句过渡语，然后显示第 2 题原文 |
| 题目文字 | 与数据库题目原文完全一致，不被 AI 改写 |
| multi_collect 题 | 回答后询问「还有没有」，输入「没了」进入下一题 |
| 最后一题回答后 | AI 显示收尾语，底部变为「提交并生成报告」按钮 |
| 跳过选填题 | 输入「跳过」可以跳过，必填题提示不可跳过 |
