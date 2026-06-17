# M2 Sprint 9 · 前端任务 · 路由懒加载与 TS 修复 v1

> 状态：✅ 已完成（2026-06-17）
> 修复类型：性能优化 + 阻塞性 TS 错误修复
> 触发场景：测试服部署后发现首屏 JS 包过大（2.2MB），且 `npm run build` 因预存 TS 错误无法通过

---

## 一、修复背景

部署到测试服 `120.26.111.136` 后，发现：

1. **前端首屏体积过大**：整个应用打包成单个 ~2.2MB 的 JS 文件，用户访问任意页面都要下载全部代码
2. **`npm run build` 失败**：暴露 `LivestreamReviewPage` / `LivestreamWriterPage` 的 3 个预存 TS 错误（dev 模式 `vite dev` 用 esbuild 不做完整类型检查，所以一直没发现）

两者都阻塞了「构建产物部署到 Nginx」的优化路径。

---

## 二、修改文件

| 文件 | 改动类型 | 改动内容 |
|------|---------|---------|
| `frontend/src/App.tsx` | 重构 | 28 个页面 `import` → `React.lazy()` + `<Suspense fallback>` 包裹 |
| `frontend/src/pages/operator/LivestreamReviewPage.tsx` | Bug 修复 | 删未用常量 `GREEN_DARK`/`GREEN_BORDER`；修 `style` 对象重复 `background` 属性 |
| `frontend/src/pages/operator/LivestreamWriterPage.tsx` | Bug 修复 | 从 import 中删未用的 `useCallback` |

---

## 三、具体改动

### 3.1 App.tsx 路由懒加载

**改造前**：所有页面静态 import，打成一个 bundle

```typescript
import HomePage from './pages/operator/HomePage';
import SellingPointPage from './pages/operator/SellingPointPage';
// ... 28 个页面

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        {/* ... */}
      </Routes>
    </BrowserRouter>
  );
}
```

**改造后**：页面 `lazy` + `<Suspense>` 包裹；Layout 和守卫保持静态

```typescript
import { lazy, Suspense } from 'react';
import AuthLayout from './layouts/AuthLayout';          // 静态（壳子，每路由都用）
import ProtectedRoute from './routes/ProtectedRoute';   // 静态（守卫，必须先跑）

const HomePage = lazy(() => import('./pages/operator/HomePage'));
const SellingPointPage = lazy(() => import('./pages/operator/SellingPointPage'));
// ... 28 个页面全部 lazy

function PageFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--gray-400)' }}>
      加载中…
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          {/* ... */}
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
```

**关键决策**：

| 项 | 决策 | 理由 |
|----|------|------|
| 28 个业务页面 | lazy | 按路由拆分，按需加载 |
| `AuthLayout` / `OperatorLayout` / `AdminLayout` | **保持静态** | 壳子，每个路由都用，lazy 反而拖慢首屏 |
| `ProtectedRoute` / `AdminRoute` | **保持静态** | 守卫必须在子组件渲染前执行 |
| `Page403` / `Page404` | **保持静态** | 本地小组件，几十行 |
| `PageFallback` 占位 | 纯 div 文字，不引入 antd Spin | fallback 进主 bundle，避免污染首屏体积 |

### 3.2 LivestreamReviewPage.tsx（3 个 TS 错误）

**错误 1+2**：定义了未使用的颜色常量

```typescript
// Before
const GREEN = '#10b981';
const GREEN_DARK = '#059669';   // ← 未使用
const GREEN_BG = '#f0fdf4';
const GREEN_BORDER = '#d1fae5'; // ← 未使用

// After
const GREEN = '#10b981';
const GREEN_BG = '#f0fdf4';
```

**错误 3**：`style` 对象字面量有两个 `background` 属性（TS1117）

```tsx
// Before — 同一对象里 background 出现两次，后面的覆盖前面的
style={{ ..., background: 'none', ..., background: GREEN_BG }}

// After — 删冗余的 background: 'none'，保留意图（GREEN_BG）
style={{ ..., background: GREEN_BG, ... }}
```

### 3.3 LivestreamWriterPage.tsx（1 个 TS 错误）

```typescript
// Before
import { useState, useRef, useEffect, useCallback } from 'react';  // ← useCallback 未用

// After
import { useState, useRef, useEffect } from 'react';
```

---

## 四、构建产物对比

### 改造前

整个应用打包成 1 个 ~2.2MB 的 JS。

### 改造后

拆成 60+ chunks，按页面加载：

| chunk 类型 | 示例 | 大小（gzip） |
|-----------|------|-------------|
| 主入口（含 Layout + 路由 + antd 核心） | `index-DVdIroUp.js` | **87 kB** |
| 登录页 | `LoginPage` | 1.3 kB |
| 卖点提取 | `SellingPointPage` | 4.9 kB |
| 红人入驻对话 | `OperatorIntakeChatPage` | 13 kB |
| 大页面（懒加载） | `HomePage` / `UsersPage` | ~106 kB / 154 kB |
| vendor（懒加载） | `xlsx` | 113 kB |

### 首屏体积

| 场景 | 改造前 | 改造后（gzip） |
|------|--------|--------------|
| 登录页首屏 | ~2.2MB | **~90 KB**（主包 87 + Login 1.3 + 少量共享 chunk） |
| 卖点提取页 | 同上 | 主包 87 + SellingPoint 4.9 ≈ **92 KB** |

**首屏缩减约 95%**，功能页按需加载，访问才下载对应 chunk。

---

## 五、测试验证

### 单元/组件测试

```
npx vitest run

Test Files  12 passed (12)
     Tests  87 passed (87)
```

无回归。仅有 React Router v7 Future Flag Warning（项目原有，与本次改动无关）。

### 构建测试

```
npm run build
✓ 3608 modules transformed.
✓ built in 15.43s
```

60+ chunks 生成成功，主入口 gzip 87 kB。

---

## 六、不涉及

- 不改 API、表结构、契约文档
- 不改业务逻辑（纯构建/路由层重构 + 删冗余代码）
- 不引入新依赖（lazy/Suspense 是 React 内置）
- dev 模式下 lazy 效果不明显（vite dev 本来就 ESM 按模块加载）；完整效果在 production build 部署后才能体现

---

## 七、部署提醒

下次部署到测试服 / 生产服后：
- 配合 Nginx gzip（`gzip_types application/javascript`）→ 每个 chunk 传输再压缩 60-80%
- chunk 文件名带 hash，可长期缓存（`expires 30d` + `Cache-Control: immutable`）
- 用户访问新页面只需下几十 KB，显著提升二次访问体验
