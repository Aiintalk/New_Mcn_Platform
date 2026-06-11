# 前端任务单 · kol-intake 对话页面重设计

> 目标：将 KOL 端对话页面（`IntakePage.tsx`）参照旧架构对话 UI 重新设计，
> 风格更现代、亲和，提升 KOL 的使用体验。
>
> 涉及文件：`src/pages/intake/IntakePage.tsx`
>
> 不涉及：逻辑、API 调用、路由均不改动，只改 UI 渲染部分

---

## 设计参考

旧架构（`kol-intake-web`）对话页面的视觉特征：
- 背景：浅灰色 `#f5f5f7`
- 顶部 header：白色，左侧圆形 AI 头像（紫色渐变 `from-purple-500 to-pink-500`），显示「红人信息采集助手」+ 进度条
- 消息气泡：AI 气泡白色 + 阴影，用户气泡紫色 `#7c3aed`（`var(--brand)` 即可）
- 气泡圆角：AI 左上角小圆角（`4px 14px 14px 14px`），用户右上角小圆角（`14px 4px 14px 14px`）
- 输入区：白色底部栏，圆角 textarea，发送按钮紫色圆角方形

新架构用系统 CSS 变量（`var(--brand)` / `var(--bg-card)` / `var(--border)` 等），不引入 Tailwind。

---

## 改动详情

### 仅改 chat phase 的渲染（`phase === 'chat'` 分支）

其余 phase（loading / expired / error / ready / submitted）的 StatusCard 保持不变。

### 改后 chat UI 结构

```tsx
// chat phase
return (
  <Shell>
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* ── Header ── */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        background: 'var(--bg-card)',
        flexShrink: 0,
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        {/* AI 头像：紫色渐变圆形 */}
        <div style={{
          width: 38, height: 38, borderRadius: '50%', flexShrink: 0,
          background: 'linear-gradient(135deg, #7c3aed, #db2777)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 14,
        }}>AI</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--gray-800)' }}>
            红人信息采集助手
          </div>
          <div style={{ fontSize: 12, color: 'var(--gray-400)' }}>
            {sending ? '正在输入…' : kolName ? `欢迎 ${kolName}` : '请如实回答，越详细越好'}
          </div>
        </div>

        {/* 进度条（消息数 / 预估总题数，仅供参考） */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <div style={{ width: 72, height: 4, background: 'var(--gray-100)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              background: 'linear-gradient(90deg, #7c3aed, #db2777)',
              borderRadius: 2,
              width: `${Math.min(100, messages.filter(m => m.role === 'user').length * 8)}%`,
              transition: 'width 0.5s ease',
            }} />
          </div>
          <span style={{ fontSize: 11, color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>
            {messages.filter(m => m.role === 'user').length} 条
          </span>
        </div>
      </div>

      {/* ── Messages ── */}
      <div style={{
        flex: 1, overflowY: 'auto',
        padding: '20px 16px',
        display: 'flex', flexDirection: 'column', gap: 14,
        background: 'var(--bg-page)',
      }}>
        {messages.map((msg, i) => (
          <div key={i} style={{
            display: 'flex',
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
            gap: 10,
            alignItems: 'flex-start',
          }}>
            {/* 头像 */}
            <div style={{
              width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
              background: msg.role === 'user'
                ? 'var(--gray-200)'
                : 'linear-gradient(135deg, #7c3aed, #db2777)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 700,
              color: msg.role === 'user' ? 'var(--gray-600)' : '#fff',
            }}>
              {msg.role === 'user' ? '我' : 'AI'}
            </div>

            {/* 气泡 */}
            <div style={{ maxWidth: '75%' }}>
              <div style={{
                background: msg.role === 'user' ? '#7c3aed' : 'var(--bg-card)',
                color: msg.role === 'user' ? '#fff' : 'var(--gray-800)',
                padding: '10px 14px',
                borderRadius: msg.role === 'user'
                  ? '14px 4px 14px 14px'
                  : '4px 14px 14px 14px',
                fontSize: 14, lineHeight: 1.65,
                boxShadow: msg.role === 'user' ? 'none' : 'var(--shadow-sm)',
                border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                whiteSpace: 'pre-wrap',
              }}>
                {msg.content}
              </div>
              <div style={{
                fontSize: 11, color: 'var(--gray-400)', marginTop: 4,
                textAlign: msg.role === 'user' ? 'right' : 'left',
              }}>
                {fmtTime(msg.ts)}
              </div>
            </div>
          </div>
        ))}

        {/* 正在输入动画 */}
        {sending && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <div style={{
              width: 32, height: 32, borderRadius: '50%',
              background: 'linear-gradient(135deg, #7c3aed, #db2777)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', fontWeight: 700, fontSize: 12, flexShrink: 0,
            }}>AI</div>
            <div style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: '4px 14px 14px 14px',
              padding: '10px 16px',
              boxShadow: 'var(--shadow-sm)',
              display: 'flex', gap: 4, alignItems: 'center',
            }}>
              {[0, 150, 300].map(delay => (
                <span key={delay} style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: '#7c3aed', display: 'inline-block',
                  animation: 'bounce 1.2s ease-in-out infinite',
                  animationDelay: `${delay}ms`,
                }} />
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div style={{
        padding: '12px 16px 16px',
        borderTop: '1px solid var(--border)',
        background: 'var(--bg-card)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="输入你的回答（Enter 发送，Shift+Enter 换行）"
            disabled={sending}
            rows={2}
            style={{
              flex: 1, resize: 'none',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: '10px 14px',
              fontFamily: 'var(--font-sans)', fontSize: 14,
              outline: 'none',
              background: 'var(--bg-page)', color: 'var(--gray-800)',
              transition: 'border-color 0.2s',
            }}
            onFocus={e => (e.target.style.borderColor = '#7c3aed')}
            onBlur={e => (e.target.style.borderColor = 'var(--border)')}
          />
          {/* 发送按钮：紫色圆角方形，SVG 箭头 */}
          <button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            style={{
              width: 44, height: 44, flexShrink: 0,
              background: '#7c3aed', border: 'none', borderRadius: 12,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer', opacity: (sending || !input.trim()) ? 0.35 : 1,
              transition: 'opacity 0.2s',
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
              stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" />
            </svg>
          </button>
        </div>

        {/* 完成并提交行 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>
            已回答 {messages.filter(m => m.role === 'user').length} 条（至少 3 条才能提交）
          </span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleSubmit}
            disabled={submitting || sending || messages.filter(m => m.role === 'user').length < 3}
            style={{ color: '#7c3aed', borderColor: '#7c3aed' }}
          >
            {submitting ? '提交中…' : '完成并生成报告 →'}
          </button>
        </div>
      </div>
    </div>
  </Shell>
);
```

### 补充跳动动画 keyframe

在 `IntakePage.tsx` 文件顶部（或 `Shell` 组件之前），注入一段全局 style：

```tsx
// 在 IntakePage 函数外，文件顶部附近
const bounceStyle = `
  @keyframes bounce {
    0%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-6px); }
  }
`;

// 在 Shell 组件里加 <style>
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-page)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <style>{bounceStyle}</style>
      <div style={{ width: '100%', maxWidth: 700, flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', minHeight: '100vh', boxShadow: 'var(--shadow-lg)' }}>
        {children}
      </div>
    </div>
  );
}
```

---

## 改动汇总

| 区域 | 改动 |
|------|------|
| Header | 头像改为紫色渐变，显示进度条（已回答条数） |
| 消息气泡 | 圆角改为「对话风格」不对称圆角，AI 头像改为渐变 |
| 正在输入 | 三点跳动动画（CSS keyframe） |
| 输入框 | 圆角加大，focus 时紫色高亮边框 |
| 发送按钮 | 改为 44×44 圆角方形 + SVG 箭头图标 |
| 逻辑 | **不改动**，所有 phase 切换、API 调用均原样保留 |

**改动量**：纯 UI 改动，约替换 chat phase return 块（80 行），TypeScript 零新 `any`，零新依赖。

---

## 完成后验证

| 验证点 | 预期 |
|--------|------|
| 进入 `/intake/:token` | 页面正常加载，进入 chat phase |
| Header | 紫色渐变 AI 头像，显示进度条 |
| AI 消息 | 白色气泡 + 阴影，左上角小圆角 |
| 用户消息 | 紫色气泡，右上角小圆角 |
| 发送消息后 | 「正在输入」三点跳动出现，回复后消失 |
| 发送按钮 | 无内容时半透明禁用，有内容时正常点击 |
| 完成后提交 | 逻辑不变，跳转 submitted / ready phase |
