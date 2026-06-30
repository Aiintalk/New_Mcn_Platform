# M2 Sprint18 前端任务 — 红人工作台（v1）

> 编写时间：2026-06-25
> 需求来源：`docs/pm/M2_Sprint18-22_红人工作台_需求文档.md` § Sprint 18
> 契约来源：`backend/docs/base/MCN_M2_Base_API.md` §24
> 前端规范：`frontend/docs/前端规范.md`（必读，动手前通读）
> 技术方案：方案 D（Shell + Module），详见需求文档 §2.4

---

## 一、任务范围

| # | 内容 | 文件 |
|---|------|------|
| 1 | API 层：千川产品库 | `src/api/qianchuanProducts.ts`（新建） |
| 2 | API 层：工作台（首页/对标/在售/人物档案） | `src/api/kolWorkspace.ts`（新建） |
| 3 | 类型定义 | `src/types/kolWorkspace.ts`（新建） |
| 4 | 路由：新增工作台路由 | `src/App.tsx`（改造） |
| 5 | 入口：KolsPage 添加「进入工作台」按钮 | `src/pages/admin/KolsPage.tsx`（改造） |
| 6 | Shell：KolWorkspacePage | `src/pages/operator/KolWorkspacePage.tsx`（新建） |
| 7 | Dashboard 模块 | `src/pages/operator/workspace/WorkspaceDashboard.tsx`（新建） |
| 8 | 千川产品库 Module | `src/pages/operator/workspace/QianchuanProductsModule.tsx`（新建） |
| 9 | 单元测试 | `src/__tests__/components/pages/KolWorkspacePage.test.tsx`（新建） |

**不做清单（本 Sprint 前端严禁越界）：**
- 不做人物档案页（Sprint 19）
- 不做素材库页（Sprint 19）
- 不做现有工具页的 Module 拆解改造（Sprint 19）
- 不做价值观仿写、复盘、成片预审（后续 Sprint）
- 工作台左侧导航中「千川仿写/价值观仿写/千川脚本预审/千川成片预审/复盘/素材库/人物档案」本期显示为**禁用灰色**占位，点击无响应（预留位置，后续 Sprint 逐步激活）

---

## 二、路由设计

在 `src/App.tsx` 新增工作台路由，位于 Operator routes 段：

```tsx
// 新增懒加载
const KolWorkspacePage = lazy(() => import('./pages/operator/KolWorkspacePage'));

// 在 Operator routes 中新增（与现有 /workspace/* 路由并列）
<Route path="/kol-workspace/:kol_id" element={<KolWorkspacePage />} />
```

> **注意**：工作台路由 `/kol-workspace/:kol_id` 使用 OperatorLayout 外壳（复用顶部栏+登录态保护），但工作台自身有独立的左侧导航，不使用 OperatorLayout 的工具列表侧边栏。
>
> 实现方式：工作台页面自带全宽布局，通过 CSS 覆盖 OperatorLayout 的侧边栏区域，或将工作台路由放在不带侧边栏的独立 Layout 中。**推荐方案：在 ProtectedRoute 下直接包 KolWorkspacePage，不嵌套 OperatorLayout，避免双侧边栏。**

```tsx
// App.tsx 调整后的 operator routes 结构
<Route element={<ProtectedRoute />}>
  {/* 工作台：独立布局，不用 OperatorLayout */}
  <Route path="/kol-workspace/:kol_id" element={<KolWorkspacePage />} />

  {/* 其他运营页面：使用 OperatorLayout */}
  <Route element={<OperatorLayout />}>
    <Route path="/" element={<HomePage />} />
    {/* ... 其他现有路由不变 ... */}
  </Route>
</Route>
```

---

## 三、类型定义（src/types/kolWorkspace.ts）

```typescript
// 千川产品
export interface QianchuanProduct {
  id: number;
  nickname: string;
  core_selling_point: string | null;
  visualization: string | null;
  mechanism: string | null;
  mechanism_exclusive: boolean;
  endorsement: string | null;
  user_feedback: string | null;
  unique_selling: string | null;
  awards: string | null;
  efficacy_proof: string | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface QianchuanProductsPage {
  items: QianchuanProduct[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

// 对标账号
export interface KolBenchmark {
  id: number;
  kol_id: number;
  account_name: string;
  account_type: 'content' | 'livestream';
  description: string | null;
  sort_order: number;
}

// 首页聚合
export interface WorkspaceDashboardData {
  kol: { id: number; name: string; avatar_url: string | null; category: string | null };
  benchmarks: { content: KolBenchmark[]; livestream: KolBenchmark[] };
  active_products: QianchuanProduct[];
}

// 人物档案
export interface PersonaDetails {
  kol_id: number;
  background: string | null;
  experience: string | null;
  relationships: string | null;
  unique_story: string | null;
  extra_notes: string | null;
  updated_at: string | null;
}

// 工作台 Tab 枚举
export type WorkspaceTab =
  | 'dashboard'
  | 'persona'         // Sprint 19
  | 'products'
  | 'qianchuan-writer'  // Sprint 19
  | 'values-writer'     // Sprint 20
  | 'script-review'     // Sprint 21
  | 'film-review'       // Sprint 23
  | 'retrospective'     // Sprint 22
  | 'references';       // Sprint 19
```

---

## 四、API 层

### src/api/qianchuanProducts.ts（新建）

```typescript
import { get, post, put, del } from './request';
import type { QianchuanProduct, QianchuanProductsPage } from '../types/kolWorkspace';

export const getQianchuanProducts = (params?: { page?: number; page_size?: number; q?: string }) =>
  get<QianchuanProductsPage>('/api/operator/qianchuan-products', params);

export const createQianchuanProduct = (data: Omit<QianchuanProduct, 'id' | 'created_by' | 'created_at' | 'updated_at'>) =>
  post<QianchuanProduct>('/api/operator/qianchuan-products', data);

export const updateQianchuanProduct = (id: number, data: Partial<QianchuanProduct>) =>
  put<QianchuanProduct>(`/api/operator/qianchuan-products/${id}`, data);

export const deleteQianchuanProduct = (id: number) =>
  del<{ id: number }>(`/api/operator/qianchuan-products/${id}`);
```

### src/api/kolWorkspace.ts（新建）

```typescript
import { get, post, put, del } from './request';
import type {
  WorkspaceDashboardData, KolBenchmark, QianchuanProduct, PersonaDetails
} from '../types/kolWorkspace';

// 首页聚合
export const getWorkspaceDashboard = (kolId: number) =>
  get<WorkspaceDashboardData>(`/api/operator/workspace/${kolId}/dashboard`);

// 对标账号
export const getBenchmarks = (kolId: number) =>
  get<{ content: KolBenchmark[]; livestream: KolBenchmark[] }>(`/api/operator/workspace/${kolId}/benchmarks`);

export const createBenchmark = (kolId: number, data: Omit<KolBenchmark, 'id' | 'kol_id'>) =>
  post<KolBenchmark>(`/api/operator/workspace/${kolId}/benchmarks`, data);

export const updateBenchmark = (kolId: number, id: number, data: Partial<KolBenchmark>) =>
  put<KolBenchmark>(`/api/operator/workspace/${kolId}/benchmarks/${id}`, data);

export const deleteBenchmark = (kolId: number, id: number) =>
  del<{ id: number }>(`/api/operator/workspace/${kolId}/benchmarks/${id}`);

// 在售商品
export const getActiveProducts = (kolId: number) =>
  get<QianchuanProduct[]>(`/api/operator/workspace/${kolId}/active-products`);

export const updateActiveProducts = (kolId: number, productIds: number[]) =>
  put<{ active_product_ids: number[] }>(`/api/operator/workspace/${kolId}/active-products`, { product_ids: productIds });

// 人物档案
export const getPersonaDetails = (kolId: number) =>
  get<PersonaDetails>(`/api/operator/kols/${kolId}/persona-details`);

export const updatePersonaDetails = (kolId: number, data: Partial<PersonaDetails>) =>
  put<PersonaDetails>(`/api/operator/kols/${kolId}/persona-details`, data);
```

---

## 五、KolsPage 改造（src/pages/admin/KolsPage.tsx）

在 KolsPage 的红人列表每行/卡片操作区新增「进入工作台」按钮：

```tsx
// 已有的操作按钮区域，追加：
import { useNavigate } from 'react-router-dom';

const navigate = useNavigate();

// 在每行 action 列或卡片按钮区追加：
<Button
  size="small"
  type="primary"
  ghost
  onClick={() => navigate(`/kol-workspace/${kol.id}`)}
>
  进入工作台
</Button>
```

> 改造量：约 5 行。不改动任何现有逻辑。

---

## 六、KolWorkspacePage Shell（src/pages/operator/KolWorkspacePage.tsx）

### 6.1 布局结构

```
┌──────────────────────────────────────────────────────┐
│ 顶部栏：[← 返回红人列表]  红人头像 + 姓名  [系统运行中] │
├──────────┬───────────────────────────────────────────┤
│ 左侧导航  │  主内容区（按 activeTab 条件渲染）          │
│ 固定宽度  │                                           │
│ 160px    │                                           │
└──────────┴───────────────────────────────────────────┘
```

### 6.2 左侧导航菜单配置

```typescript
const NAV_ITEMS: { tab: WorkspaceTab; label: string; icon: ReactNode; disabled?: boolean }[] = [
  { tab: 'dashboard',        label: '工作台首页', icon: <HomeOutlined /> },
  { tab: 'persona',          label: '人物档案',   icon: <UserOutlined />,        disabled: true },  // Sprint 19
  { tab: 'products',         label: '产品库',     icon: <ShoppingOutlined /> },
  { tab: 'qianchuan-writer', label: '千川仿写',   icon: <ScissorOutlined />,     disabled: true },  // Sprint 19
  { tab: 'values-writer',    label: '价值观仿写', icon: <HeartOutlined />,       disabled: true },  // Sprint 20
  { tab: 'script-review',    label: '千川脚本预审', icon: <SearchOutlined />,    disabled: true },  // Sprint 21
  { tab: 'film-review',      label: '千川成片预审', icon: <VideoCameraOutlined />, disabled: true }, // Sprint 23
  { tab: 'retrospective',    label: '复盘',       icon: <BarChartOutlined />,    disabled: true },  // Sprint 22
  { tab: 'references',       label: '素材库',     icon: <FolderOutlined />,      disabled: true },  // Sprint 19
];
```

禁用项：`cursor: not-allowed; opacity: 0.4;`，点击无响应（不 setActiveTab）。

### 6.3 状态与数据加载

```typescript
// 从 URL 参数读取 kol_id
const { kol_id } = useParams<{ kol_id: string }>();
const kolId = Number(kol_id);

// activeTab 状态（默认首页）
const [activeTab, setActiveTab] = useState<WorkspaceTab>('dashboard');

// kol 基本信息（顶部栏展示用）
const [kolName, setKolName] = useState('');
const [kolAvatar, setKolAvatar] = useState<string | null>(null);
```

顶部栏的 kol 信息从 dashboard 接口返回的 `data.kol` 中读取，避免额外请求。WorkspaceDashboard 加载完成后通过 props 回调或直接传到父组件。

### 6.4 主内容区条件渲染

```tsx
<main>
  {activeTab === 'dashboard' && <WorkspaceDashboard kolId={kolId} onKolLoaded={(kol) => { setKolName(kol.name); setKolAvatar(kol.avatar_url); }} />}
  {activeTab === 'products'  && <QianchuanProductsModule />}
  {/* 以下 Sprint 19+ 实现，本期不渲染 */}
  {/* activeTab === 'persona' && <WorkspacePersona kolId={kolId} /> */}
  {/* ... */}
</main>
```

---

## 七、WorkspaceDashboard 模块（src/pages/operator/workspace/WorkspaceDashboard.tsx）

### 7.1 Props

```typescript
interface WorkspaceDashboardProps {
  kolId: number;
  onKolLoaded?: (kol: { name: string; avatar_url: string | null }) => void;
}
```

### 7.2 数据加载

初始化时调用 `getWorkspaceDashboard(kolId)`，loading 态显示骨架屏（Ant Design Skeleton）。

### 7.3 对标账号区域

```
┌──────────────────┐  ┌──────────────────┐
│ 内容对标（N个）   │  │ 直播对标（N个）   │
│ · 账号名  [内容]  │  │ · 账号名  [直播]  │
│   简介一句话      │  │   简介一句话      │
└──────────────────┘  └──────────────────┘
[+ 添加对标账号]
```

**交互：**
- 点账号卡片 → 弹出 Modal 编辑（账号名/类型/简介）
- 悬浮账号卡片 → 右上角显示删除图标（Popconfirm 二次确认）
- 「+ 添加对标账号」→ 弹出 Modal 新建
- Modal 表单字段：账号名（Input，必填）、类型（Radio: 内容对标/直播对标）、简介（TextArea，选填）

**数据操作：** 调用 `createBenchmark` / `updateBenchmark` / `deleteBenchmark`，成功后重新 fetch dashboard。

### 7.4 目前在售商品区域

```
在售商品                      [管理商品]
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 夏日控油  │ │ 大红瓶    │ │   ...    │
│ 美妆 主推 │ │ 美白  背书│ │          │
│ 控油持妆  │ │ 明星同款  │ │          │
└──────────┘ └──────────┘ └──────────┘
```

**商品卡片字段展示：**
- 标题：`nickname`（加粗）
- Tag 行：`core_selling_point`（若有），`mechanism_exclusive=true` 时显示「只有我有」红色 Tag
- 内容：`mechanism`（截断 40 字）
- 鼠标 hover 显示「移除」按钮

**「管理商品」按钮** → 弹出 Modal：
- 左侧：全量产品列表（分页，可搜索），Checkbox 勾选
- 右侧：已选列表预览
- 确认后调 `updateActiveProducts(kolId, selectedIds)`

**Modal 内提供「+ 新建产品」快捷入口** → 跳转到 `/kol-workspace/:kol_id`（activeTab='products'），或内嵌新建弹窗（推荐内嵌，不离开当前页面）。

---

## 八、QianchuanProductsModule（src/pages/operator/workspace/QianchuanProductsModule.tsx）

### 8.1 功能

全局千川产品库 CRUD（不绑定达人）。

### 8.2 列表页

- Ant Design Table，列：昵称、最主推卖点、主推机制、「只有我有」tag、操作（编辑/删除）
- 顶部：搜索框（nickname 模糊搜索）+ 「+ 新建产品」按钮
- 分页（每页 20 条）
- 软删除后从列表消失

### 8.3 新建/编辑弹窗（ProductFormModal）

Ant Design Modal + Form，字段：

| 字段 | 组件 | 必填 |
|------|------|------|
| 产品昵称 | Input | ✅ |
| 最主推卖点 | Input | |
| 可视化演示点 | TextArea (rows=3) | |
| 主推机制 | TextArea (rows=3) | |
| 只有我有 | Checkbox（在主推机制下方） | |
| 推荐来源/背书 | TextArea (rows=3) | |
| 用户反馈 | TextArea (rows=3) | |
| 独家卖点 | TextArea (rows=3) | |
| 获奖荣誉 | Input | |
| 功效承诺 | TextArea (rows=3) | |

### 8.4 删除

Table 操作列「删除」→ Popconfirm 确认 → 调 `deleteQianchuanProduct`。

---

## 九、单元测试（src/__tests__/components/pages/KolWorkspacePage.test.tsx）

**必须覆盖：**
1. Shell 正常渲染（顶部栏显示、左侧导航显示）
2. 默认展示 Dashboard（activeTab='dashboard'）
3. 点击产品库切换到 QianchuanProductsModule
4. 禁用 Tab（人物档案/千川仿写等）点击后 activeTab 不变
5. WorkspaceDashboard：对标账号正常展示（mock API 返回）
6. WorkspaceDashboard：在售商品正常展示
7. QianchuanProductsModule：列表展示
8. QianchuanProductsModule：新建弹窗表单校验（nickname 必填）
9. API 错误时显示错误状态（非 crash）

Mock 策略：所有 API 调用用 `vi.mock` mock，不依赖后端。

---

## 十、开发红线核查（完成后自查）

- [ ] 所有 JSON API 调用走 `request.ts`（`import { get, post, put, del } from './request'`），无裸 `fetch`
- [ ] 无未处理的 Promise rejection（loading/error 状态均有处理）
- [ ] 禁用 Tab 点击无响应（不报错、不跳转）
- [ ] `kol_id` 非法（NaN）时 graceful 处理（导航到 404 或显示错误）
- [ ] 新文件遵循现有命名与目录约定
- [ ] 新增路由已在 App.tsx 注册

---

## 十一、验收口径

1. `npx vitest run src/__tests__/components/pages/KolWorkspacePage.test.tsx` 全部通过
2. 从 KolsPage 点击「进入工作台」能进入对应达人工作台
3. 工作台首页展示对标账号和在售商品（联调后端后验证）
4. 对标账号 CRUD 功能正常（增/改/删）
5. 在售商品管理弹窗：勾选/取消商品后保存生效
6. 千川产品库：列表展示、新建、编辑、删除均正常
7. 禁用 Tab（人物档案等）灰色显示，点击无响应
8. 浏览器 console 无未捕获错误
