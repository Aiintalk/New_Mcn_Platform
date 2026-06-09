# 前端任务单 · OperatorIntakeChatPage 布局修复

> 问题：运营端红人信息采集助手页面
> 1. 标题 Header 不固定，会随消息列表一起滚动
> 2. 输入框下方有大量留白
>
> 涉及文件：
> - `src/pages/operator/OperatorIntakeChatPage.tsx`

---

## 根因分析

`OperatorIntakeChatPage` 嵌套在 `OperatorLayout` 里，OperatorLayout 的结构是：

```
.app-shell                     ← 全屏 flex
  .main-content                ← flex: 1, overflow: hidden
    .topbar                    ← height: 52px, flex-shrink: 0
    .main-body                 ← flex: 1, overflow-y: auto, padding: 24px
      <OperatorIntakeChatPage> ← 渲染在这里
```

**问题 1**：Header 用了 `position: sticky`，但 `.main-body` 已经是滚动容器（`overflow-y: auto`），sticky 在自身滚动容器内无效，Header 跟着消息一起滚走了。

**问题 2**：`Shell` 组件内层用了 `minHeight: '100vh'`，但页面已经被 `OperatorLayout` 包裹，实际可用高度 = `100vh - topbar(52px) - main-body padding(48px)`。`minHeight: 100vh` 远超可用高度，撑出大量空白。

---

## 改动方案

### 改动 1 — 修改 Shell 组件

**当前代码（第 421-430 行）：**

```tsx
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

**修改为：**

```tsx
function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ height: '100%', background: 'var(--bg-page)', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <style>{bounceStyle}</style>
      <div style={{ width: '100%', maxWidth: 700, flex: 1, display: 'flex', flexDirection: 'column', background: 'var(--bg-card)', height: '100%', boxShadow: 'var(--shadow-lg)' }}>
        {children}
      </div>
    </div>
  );
}
```

变更：`minHeight: '100vh'` → `height: '100%'`（两处都改）

---

### 改动 2 — .main-body 去除 padding（仅对此页生效）

`.main-body` 的 `padding: 24px` 会在对话页四周产生边距，而且与 `height: 100%` 配合时还会产生额外留白。

在 `OperatorIntakeChatPage` 挂载/卸载时动态设置 `.main-body` 的 padding 为 0：

```tsx
// 在组件内 useEffect 里加（与初始化 useEffect 分开写）：
useEffect(() => {
  const mainBody = document.querySelector('.main-body') as HTMLElement | null;
  if (mainBody) {
    mainBody.style.padding = '0';
    mainBody.style.overflow = 'hidden';
  }
  return () => {
    if (mainBody) {
      mainBody.style.padding = '';
      mainBody.style.overflow = '';
    }
  };
}, []);
```

---

### 改动 3 — 对话区高度撑满

对话页根节点（第 189 行）当前是 `height: '100%'`，保持不变，但要确保 Shell 的父容器能正确传递高度。

在 `OperatorLayout` 的 `.main-body` 中，`overflow-y: auto` 改为 `overflow: hidden`（由改动 2 的 JS 在此页动态设置，无需改 CSS 文件）。

---

## 验证点

| 验证 | 预期 |
|------|------|
| 进入红人信息采集助手页 | Header（含「AI」头像 + 标题 + 创建分享链接按钮）固定在顶部不随消息滚动 |
| 消息列表滚动 | 只有消息区域滚动，Header 和输入框保持固定 |
| 输入框下方 | 无多余留白，输入框紧贴页面底部 |
| 退出此页跳转其他页 | `.main-body` 的 padding 和 overflow 恢复正常（其他页不受影响） |
