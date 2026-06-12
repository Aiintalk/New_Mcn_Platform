# M2 Sprint 3 — 对标分析助手 前端 + 测试基础设施 Bug 修复

> 日期：2026-06-12
> 范围：benchmark 前端 UI 修复 + 测试环境修复 + antd 废弃 API 修复
> 结果：371/371 测试通过，0 失败

---

## Bug 1：复制按钮灰色不可见

**现象：** 对标分析结果页点击"复制"按钮，按钮颜色过灰，视觉上看起来像禁用状态。

**根因：** 按钮样式使用 `color: var(--gray-400)` + `background: var(--gray-50)`，灰色调在浅色背景上几乎不可见。

**修复：**
```diff
- color: 'var(--gray-400)', background: 'var(--gray-50)', border: '1px solid var(--gray-200)',
+ color: 'var(--primary-600)', background: 'var(--primary-50)', border: '1px solid var(--primary-200)',
```

**文件：** `frontend/src/pages/operator/BenchmarkPage.tsx`

---

## Bug 2：antd `destroyOnClose` 废弃警告

**现象：** 浏览器 console 报 warning：
```
Warning: [antd: Modal] `destroyOnClose` is deprecated. Please use `destroyOnHidden` instead.
```

**根因：** antd v5 将 `destroyOnClose` 重命名为 `destroyOnHidden`，旧属性仍可用但会触发警告。

**修复：** 6 处 `destroyOnClose` → `destroyOnHidden`

| 文件 | 处数 |
|------|------|
| `frontend/src/pages/admin/BenchmarkConfigTab.tsx` | 1 |
| `frontend/src/pages/admin/AdminIntakePage.tsx` | 3 |
| `frontend/src/pages/operator/OperatorIntakeChatPage.tsx` | 1 |
| `frontend/src/pages/operator/TasksPage.tsx` | 1 |

---

## Bug 3：antd `message` 静态方法缺少 context

**现象：** 浏览器 console 报 warning：
```
Warning: [antd: message] Static function can not consume context like dynamic theme. Please use 'App' component instead.
```

**根因：** 代码使用 `import { message } from 'antd'` 静态方法调用，无法消费 `<App>` 组件提供的动态主题 context。

**修复：**
```diff
- import { message } from 'antd';
+ import { App } from 'antd';

  export default function BenchmarkPage() {
+   const { message } = App.useApp();
```

**文件：** `frontend/src/pages/operator/BenchmarkPage.tsx`

**备注：** 全项目约 25 个文件使用静态 `message`，本次仅修复 BenchmarkPage。其余文件待批量迁移。

---

## Bug 4：tab 按钮 border 属性冲突

**现象：** 浏览器 console 报 warning：
```
Updating a style property during rerender (borderBottom) when a conflicting property is set (border) can lead to styling bugs.
```

**根因：** tab 按钮同时设置 `border: 'none'` 和动态 `borderBottom`，React 检测到简写属性与独立属性冲突。

**修复：**
```diff
- border: 'none',
- borderBottom: activeTab === 'profile' ? '2px solid var(--primary-600)' : '2px solid transparent',
+ borderTop: 'none', borderLeft: 'none', borderRight: 'none',
+ borderBottom: activeTab === 'profile' ? '2px solid var(--primary-600)' : '2px solid transparent',
```

**文件：** `frontend/src/pages/operator/BenchmarkPage.tsx`

---

## Bug 5：jsdom 缺少 `window.matchMedia`（测试环境）

**现象：** 5 个 LoginPage 测试全部 FAIL：
```
TypeError: window.matchMedia is not a function
```

**根因：** Ant Design 的 `responsiveObserver` 调用 `window.matchMedia`，但 jsdom 不提供此 API。

**修复：** `frontend/src/test/setup.ts` 添加 mock：
```ts
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
```

---

## Bug 6：Sprint 3 模型未注册导致集成测试失败

**现象：** 40 个集成测试全部 ERROR，`Base.metadata.create_all` 无法创建 Sprint 3 新增的表。

**根因：** `app/models/__init__.py` 缺少 Sprint 3 新增模型的 import，SQLAlchemy 的 `Base.metadata` 不知道这些模型存在。

**修复：** 补全 import：
```python
from app.models.credential import ServiceCredential, AiModel
from app.models.tikhub_credential import TikHubCredential
from app.models.tikhub_call_log import TikHubCallLog
from app.models.benchmark import BenchmarkConfig, BenchmarkAnalysis
```

**文件：** `backend/app/models/__init__.py`

---

## Bug 7：operator_benchmark 调用旧函数名（tikhub 重构隐患）

**现象：** `operator_benchmark.py` 调用 `get_top10`、`get_recent30days`、`format_videos` 三个旧函数名。当前因旧函数仍在 tikhub.py 中未删除，功能正常，但属于隐患。

**根因：** tikhub.py 重构后保留了两套函数（旧 benchmark 专用 + 新 persona 专用），`operator_benchmark.py` 未同步更新调用。

**修复：**
```diff
- top10 = tikhub_adapter.get_top10(videos)
- recent30 = tikhub_adapter.get_recent30days(videos)
- top10_text = tikhub_adapter.format_videos(top10, "全账号点赞TOP10")
- recent30_text = tikhub_adapter.format_videos(recent30, "最近30天内容")
+ top10 = tikhub_adapter.get_top10_videos(videos)
+ recent30 = tikhub_adapter.get_recent_30day_videos(videos)
+ top10_text = tikhub_adapter.format_videos_text(top10, "全账号点赞TOP10")
+ recent30_text = tikhub_adapter.format_videos_text(recent30, "最近30天内容")
```

**文件：** `backend/app/routers/operator_benchmark.py`

---

## Bug 8：迁移脚本编号冲突

**现象：** benchmark 迁移脚本编号为 `007_benchmark.sql`，与已有的 `007_kol_intake_operator_sessions.sql` 冲突。

**根因：** Sprint 3 开发时 007 已被 Sprint 1 占用，benchmark 迁移应使用 013。

**修复：** `007_benchmark.sql` → `013_benchmark.sql`

**文件：** `backend/migrations/013_benchmark.sql`

---

## 影响范围

| Bug | 影响范围 | 是否回归 |
|-----|---------|---------|
| Bug 1 | 仅 BenchmarkPage | 否 |
| Bug 2 | 6 个 Modal 组件 | 否 |
| Bug 3 | 仅 BenchmarkPage | 否 |
| Bug 4 | 仅 BenchmarkPage | 否 |
| Bug 5 | 全部前端测试 | 否 |
| Bug 6 | 全部集成测试 | 否 |

---

## 验证结果

```
后端：289 passed
前端：82 passed
合计：371 passed, 0 failed
覆盖率：54.22%（门禁 10%）
```
