# M2 Sprint 1 · kol-intake 对话页 UX 修复 v1 · 修复Bug

> 状态：✅ 已完成（2026-06-17）
> 前序文档：`M2_Sprint1_kol_intake_*.md` 系列
> 修复类型：UX 体验问题（2 个）

---

## 一、修复背景

人工测试 `/workspace/kol-intake/chat` 时发现 2 个 UX 问题：

### 问题 1：回车发送后输入框失焦

**现象**：用户回答一个问题按回车发送后，下个问题要继续回答时，输入框需要再点击一下才能继续输入。

**根因**：textarea 用了 `disabled={sending}` 控制发送期间禁用。当 `sending` 从 `true` 变回 `false` 时，textarea 从 disabled 状态恢复，但 DOM 焦点没有自动回到输入框，焦点丢到了 `<body>`。

### 问题 2：报告页没有"重新采集"按钮

**现象**：进入报告展示阶段（step=ready）后，整个页面只显示 AI 生成的报告 + 下载按钮，没有"我想重新走一遍流程"的入口。用户必须手动改 URL 才能重新开始。

**根因**：原设计报告页是终点，没考虑「运营想用同一个 session 重做一次」的场景。

---

## 二、修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/pages/operator/OperatorIntakeChatPage.tsx` | 加 `inputRef` + `useEffect` 自动 focus；抽 `initSession()` 函数；报告页加"重新采集"按钮 |

---

## 三、具体改动

### 3.1 修复输入框失焦

**新增 ref 和 effect**：

```typescript
const inputRef = useRef<HTMLTextAreaElement>(null);

// sending 结束后自动 focus 回输入框
useEffect(() => {
  if (!sending) inputRef.current?.focus();
}, [sending]);
```

**textarea 绑定 ref**：

```tsx
<textarea
  ref={inputRef}
  value={input}
  onChange={...}
  disabled={sending}
  // ...
/>
```

**效果**：发送完成（`sending` 从 true → false）时，焦点自动回到输入框，用户可立即继续打字。

### 3.2 抽取 `initSession()` 函数

**改造前**：mount 时的初始化逻辑和「重新采集」需要的初始化逻辑重复，难以复用。

**改造后**：抽成独立函数，两处共用

```typescript
const initSession = useCallback(() => {
  // 重置 state：step / answers / report / sending / error 全部归位
  setStep('chat');
  setAnswers([]);
  setReport('');
  setError('');
  // 重新请求 session token（如果需要）
  // ...
}, [...]);

// mount 时调用
useEffect(() => {
  initSession();
}, [initSession]);
```

### 3.3 报告页加"重新采集"按钮

在报告展示阶段（step === 'ready'）的头部加按钮：

```tsx
{step === 'ready' && (
  <button
    className="btn btn-ghost btn-sm"
    onClick={() => initSession()}
  >
    重新采集
  </button>
)}
```

**样式选择 `btn-ghost`**：与"下载报告"等主操作区分，作为次要操作。

---

## 四、测试验证

### 手动验证

| # | 步骤 | 期望 |
|---|------|------|
| 1 | 进入 `/workspace/kol-intake/chat`，回答第一个问题回车 | 输入框保持焦点，可直接输入下个答案 |
| 2 | 连续回答 24 个问题 | 全程无需点击输入框 |
| 3 | 走完流程进入报告页 | 看到「重新采集」按钮 |
| 4 | 点「重新采集」 | 状态归位，回到对话第一步 |

### 自动化测试

前端测试套件 `npx vitest run` 87/87 全通过，无回归。

---

## 五、不涉及

- 不改后端 API（无需新接口/新参数）
- 不改 session 机制（沿用原有 token 流程）
- 不改报告生成逻辑（只加 UX 入口）
- 不改契约文档
