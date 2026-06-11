# MCN_Frontend_Agent — M2 Sprint 2 补充任务2（管理端使用日志页面）

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-09  
> 前置条件：后端 M2 Sprint 2 补充2 接口已就绪  
> 完成后：回传 PM

---

## 背景

管理端新增「使用日志」页面，供管理员查看各运营人员的功能使用记录。  
入口：管理端「工具配置」→「使用日志」（或同级菜单，参照现有管理端菜单结构放置）。

---

## 一、新增文件

```
frontend/src/
├── pages/admin/
│   └── UsageLogPage.tsx     # 使用日志页面
└── api/
    └── adminUsageLog.ts     # API 调用层
```

---

## 二、API 层（api/adminUsageLog.ts）

```typescript
const BASE = '/api/admin/usage-logs';

export interface UsageLogItem {
  user_id: number;
  username: string;
  display_name: string;
  feature: string;
  feature_name: string;
  created_at: string;
}

export interface UsageLogListResponse {
  total: number;
  page: number;
  page_size: number;
  items: UsageLogItem[];
}

export interface UsageLogSummary {
  date_from: string;
  date_to: string;
  total_count: number;
  by_feature: { feature: string; feature_name: string; count: number }[];
  by_user: { user_id: number; username: string; display_name: string; count: number }[];
}

export interface UsageLogQuery {
  page?: number;
  page_size?: number;
  user_id?: number;
  feature?: string;
  date_from?: string;
  date_to?: string;
}

export async function getUsageLogs(query: UsageLogQuery): Promise<UsageLogListResponse>
export async function getUsageLogSummary(params: { date_from?: string; date_to?: string }): Promise<UsageLogSummary>
```

---

## 三、页面（pages/admin/UsageLogPage.tsx）

### 3.1 页面布局

```
┌─────────────────────────────────────────────────────┐
│ 使用日志                                              │  ← 页面标题
├──────────────┬──────────────────────────────────────┤
│ 汇总统计卡片  │  功能使用分布（水平条形图或数字列表）  │  ← 顶部汇总行
├─────────────────────────────────────────────────────┤
│  筛选栏：[运营人员 ▼] [功能 ▼] [日期范围]  [查询]   │  ← 筛选
├─────────────────────────────────────────────────────┤
│  日志列表（表格）                                     │  ← 主体
│  运营人员 | 功能 | 时间                               │
│  ...                                                 │
│  分页                                                 │
└─────────────────────────────────────────────────────┘
```

---

### 3.2 顶部汇总区

加载 `getUsageLogSummary`（默认最近30天），展示：

**左侧：3个统计数字**
- 总使用次数：`{total_count} 次`
- 功能种类：`{by_feature.length} 个`
- 活跃运营：`{by_user.length} 人`

**右侧：功能使用分布**

按 `by_feature` 数据展示各功能使用次数，用 Ant Design `Progress` 条形或简单数字列表：

```tsx
{summary.by_feature.map(item => (
  <div key={item.feature} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
    <span style={{ fontSize: 13, color: 'var(--gray-600)' }}>{item.feature_name}</span>
    <span style={{ fontSize: 13, fontWeight: 600 }}>{item.count} 次</span>
  </div>
))}
```

---

### 3.3 筛选栏

```tsx
// 筛选状态
const [filterUserId, setFilterUserId] = useState<number | undefined>();
const [filterFeature, setFilterFeature] = useState<string | undefined>();
const [filterDateRange, setFilterDateRange] = useState<[string, string] | undefined>();
const [page, setPage] = useState(1);
```

筛选组件（使用 Ant Design）：
- **运营人员**：`Select` 下拉，选项从 `GET /api/admin/users`（已有接口）拉取，展示 display_name
- **功能**：`Select` 下拉，固定选项：
  ```
  全部 / 红人入驻问卷(kol-intake) / 人格定位(persona-positioning) / 其他工具(other)
  ```
- **日期范围**：Ant Design `RangePicker`，格式 `YYYY-MM-DD`
- **查询按钮**：点击触发 `loadLogs()`，重置 page=1

---

### 3.4 日志列表表格

使用 Ant Design `Table`：

```tsx
const columns = [
  {
    title: '运营人员',
    dataIndex: 'display_name',
    render: (name: string, row: UsageLogItem) => `${name}（${row.username}）`,
  },
  {
    title: '功能',
    dataIndex: 'feature_name',
    render: (name: string, row: UsageLogItem) => (
      <span style={{
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        background: featureBgColor(row.feature),
        color: featureColor(row.feature),
      }}>
        {name}
      </span>
    ),
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    render: (ts: string) => new Date(ts).toLocaleString('zh-CN', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    }),
  },
];
```

功能标签颜色：
```typescript
function featureBgColor(feature: string) {
  if (feature === 'kol-intake') return 'rgba(124,58,237,0.1)';
  if (feature === 'persona-positioning') return 'rgba(219,39,119,0.1)';
  return 'rgba(107,114,128,0.1)';
}
function featureColor(feature: string) {
  if (feature === 'kol-intake') return '#7c3aed';
  if (feature === 'persona-positioning') return '#db2777';
  return '#6b7280';
}
```

分页：`Pagination` 组件，`total` 来自接口 `total` 字段，`pageSize=20`。

---

### 3.5 数据加载

```typescript
const loadLogs = useCallback(async () => {
  setLoading(true);
  try {
    const res = await getUsageLogs({
      page,
      page_size: 20,
      user_id: filterUserId,
      feature: filterFeature,
      date_from: filterDateRange?.[0],
      date_to: filterDateRange?.[1],
    });
    setLogs(res.items);
    setTotal(res.total);
  } catch {
    message.error('加载失败');
  } finally {
    setLoading(false);
  }
}, [page, filterUserId, filterFeature, filterDateRange]);

useEffect(() => { loadLogs(); }, [loadLogs]);
```

---

## 四、路由注册

在 `App.tsx` 中注册管理端路由（需在管理员守卫内）：

```typescript
<Route path="/admin/usage-logs" element={<UsageLogPage />} />
```

---

## 五、导航菜单

找到管理端侧边栏菜单配置，在「工具配置」下（或同级）新增：

```typescript
{ key: 'usage-logs', label: '使用日志', path: '/admin/usage-logs' }
```

---

## 六、验收标准

1. 顶部汇总区显示总次数、功能分布（默认最近30天）
2. 筛选「运营人员」后列表只显示该运营的记录
3. 筛选「功能=红人入驻问卷」后只显示 kol-intake 记录
4. 日期范围筛选生效
5. 分页正常，20条/页
6. 非管理员账号访问跳转至无权限页或首页
