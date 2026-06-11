# 前端任务单 · kol-intake 运营直发 submit 接口传递消息

> 配合后端任务 `M2_Sprint1_kol_intake_submit保存消息.md`
> 提交时把完整对话消息列表一并发给后端，让 AI 有数据可以生成报告。
>
> 涉及文件：
> - `src/api/intakeDirect.ts`
> - `src/pages/operator/OperatorIntakeChatPage.tsx`

---

## 改动 1 — intakeDirect.ts：submitDirect 接受 messages 参数

**改前**：
```ts
export const submitDirect = (sessionId: number) =>
  post<{ report_status: string }>(
    `/api/operator/intake/direct/${sessionId}/submit`, {}
  );
```

**改后**：
```ts
export const submitDirect = (sessionId: number, messages: ChatMessage[]) =>
  post<{ report_status: string }>(
    `/api/operator/intake/direct/${sessionId}/submit`,
    { messages }
  );
```

注意 `ChatMessage` 已在文件顶部从 `'../types/intake'` 导入（现有 import 保持不变）。

---

## 改动 2 — OperatorIntakeChatPage.tsx：handleSubmit 传入 messages

**改前**（第 210-222 行）：
```tsx
async function handleSubmit() {
  if (!sessionId || !done) return;
  setSubmitting(true);
  try {
    await submitDirect(sessionId);
    setPhase('submitted');
    pollStatus(sessionId);
  } catch (err: unknown) {
    message.error((err as Error).message || '提交失败，请重试');
  } finally {
    setSubmitting(false);
  }
}
```

**改后**：
```tsx
async function handleSubmit() {
  if (!sessionId || !done) return;
  setSubmitting(true);
  try {
    await submitDirect(sessionId, messages);  // 传入当前消息列表
    setPhase('submitted');
    pollStatus(sessionId);
  } catch (err: unknown) {
    message.error((err as Error).message || '提交失败，请重试');
  } finally {
    setSubmitting(false);
  }
}
```

只改一处：`submitDirect(sessionId)` → `submitDirect(sessionId, messages)`

---

## 改动汇总

| 文件 | 改动 |
|------|------|
| `intakeDirect.ts` | `submitDirect` 增加 `messages` 参数并发送到后端 |
| `OperatorIntakeChatPage.tsx` | 调用 `handleSubmit` 时传入 `messages` |

**改动量**：约 3 行，配合后端修复一起生效。

---

## 验收

| 验证点 | 预期 |
|--------|------|
| 完成问答后提交报告 | 报告包含真实回答内容（人物画像、表达风格等有具体内容） |
| 报告不出现 | "目前还没有拿到完整的对话记录" 或"暂无（需要基于真实对话提炼）" |
