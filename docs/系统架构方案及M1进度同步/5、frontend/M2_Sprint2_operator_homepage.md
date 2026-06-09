# MCN_Frontend_Agent — M2 Sprint 2 任务指令（运营端首页重设计）

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-08  
> 前置条件：M1 全部验收通过，后端 M2 Sprint 2 接口已就绪  
> 完成后：回传 PM

---

## M2 Sprint 2 目标

重设计运营端首页 `src/pages/operator/HomePage.tsx`，新增数据统计卡片、内容趋势图、个人使用情况。

---

## 一、新页面布局

```
┌─────────────────────────────────────────────────────────┐
│  早上好，张三                                [开始创作]   │  ← 顶部欢迎区（现有，保留）
│  欢迎回到达人说 AI 内容运营平台                          │
├────────────────────────────────────────────────────────  │
│  [今日产出 3]  [本周产出 18]  [进行中任务 2]  [Token用量 45.2K] │  ← 工作概览（4卡片）
├─────────────────────────────┬──────────────────────────  │
│  最近7天内容产出趋势（折线图） │  个人使用情况             │  ← 2列
│                             │  本周工具使用：12次         │
│                             │  最近使用工具：爆款标题...  │
│                             │  最近登录：06-08 09:00      │
├─────────────────┬───────────┴──────────────────────────  │
│  最近任务        │  最近产出                              │  ← 底部保留（现有）
└─────────────────┴────────────────────────────────────────┘
```

---

## 二、API 层

在 `src/api/outputs.ts` 或新建 `src/api/homepage.ts` 中添加：

```typescript
// src/api/homepage.ts
import { request } from './request'

export interface HomepageStats {
  today_outputs: number
  week_outputs: number
  in_progress_tasks: number
  week_token_usage: number | null
  week_tool_count: number
  recent_tools: { tool_name: string; tool_code: string; last_used_at: string }[]
  last_login_at: string | null
}

export interface HomepageTrend {
  trend: { date: string; count: number }[]
}

export const getHomepageStats = (): Promise<HomepageStats> =>
  request.get('/api/operator/homepage/stats')

export const getHomepageTrend = (): Promise<HomepageTrend> =>
  request.get('/api/operator/homepage/trend')
```

---

## 三、页面改造（`src/pages/operator/HomePage.tsx`）

### 3.1 State 新增

```typescript
const [stats, setStats] = useState<HomepageStats | null>(null)
const [trend, setTrend] = useState<{ date: string; count: number }[]>([])
const [statsLoading, setStatsLoading] = useState(true)
```

### 3.2 数据加载

将现有 `useEffect` 改为同时拉取 4 个接口（stats / trend / tasks / outputs），两组独立加载，互不阻塞：

```typescript
useEffect(() => {
  // 统计数据（独立加载）
  Promise.all([getHomepageStats(), getHomepageTrend()])
    .then(([s, t]) => { setStats(s); setTrend(t.trend) })
    .catch(() => message.error('加载统计数据失败'))
    .finally(() => setStatsLoading(false))

  // 最近任务/产出（独立加载，现有逻辑保留）
  Promise.all([getTasks({ page: 1, page_size: 5 }), getOutputs({ page: 1, page_size: 5 })])
    .then(([t, o]) => { setTasks(t.items); setOutputs(o.items) })
    .catch(() => message.error('加载首页数据失败'))
    .finally(() => setLoading(false))
}, [])
```

### 3.3 工作概览 — 4 张统计卡片

布局：`grid-template-columns: repeat(4, 1fr)`，间距 `var(--sp-4)`

```tsx
<div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--sp-4)' }}>
  <StatCard label="今日产出" value={stats?.today_outputs ?? 0} unit="篇" loading={statsLoading} />
  <StatCard label="本周产出" value={stats?.week_outputs ?? 0} unit="篇" loading={statsLoading} />
  <StatCard label="进行中任务" value={stats?.in_progress_tasks ?? 0} unit="个" loading={statsLoading} />
  <StatCard
    label="Token 用量"
    value={stats?.week_token_usage != null ? formatToken(stats.week_token_usage) : '—'}
    unit={stats?.week_token_usage != null ? '' : ''}
    sub="本周"
    loading={statsLoading}
  />
</div>
```

**StatCard 内联组件**（在 HomePage.tsx 文件内定义，不单独抽文件）：

```tsx
function StatCard({ label, value, unit, sub, loading }: {
  label: string
  value: string | number
  unit?: string
  sub?: string
  loading?: boolean
}) {
  return (
    <div className="card" style={{ padding: 'var(--sp-4)' }}>
      <div style={{ color: 'var(--gray-500)', fontSize: 13, marginBottom: 8 }}>{label}</div>
      {loading
        ? <div style={{ height: 32, background: 'var(--gray-100)', borderRadius: 4 }} />
        : <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--gray-900)', lineHeight: 1.2 }}>
            {value}<span style={{ fontSize: 13, color: 'var(--gray-500)', marginLeft: 4 }}>{unit}</span>
          </div>
      }
      {sub && <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}
```

**Token 格式化工具函数**（文件内定义）：

```typescript
function formatToken(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}
```

---

### 3.4 中间行 — 趋势图 + 个人使用情况

布局：`grid-template-columns: 2fr 1fr`

#### 趋势图（左侧）

使用项目已有的图表库。

**确认图表库方式：** 查看 `package.json`：
- 若有 `recharts` → 使用 `LineChart` / `Line` / `XAxis` / `YAxis` / `Tooltip`
- 若有 `@ant-design/charts` → 使用 `Line` 组件
- 若都没有 → 优先安装 `recharts`（`npm install recharts`）

**recharts 实现参考：**

```tsx
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

// 趋势图卡片
<div className="card">
  <div className="card-header">
    <h3 className="card-title">内容产出趋势</h3>
    <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>最近7天</span>
  </div>
  {statsLoading
    ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
    : <ResponsiveContainer width="100%" height={200}>
        <LineChart data={trend}>
          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} width={30} />
          <Tooltip />
          <Line type="monotone" dataKey="count" stroke="var(--brand-500)" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
  }
</div>
```

#### 个人使用情况（右侧）

```tsx
<div className="card">
  <div className="card-header">
    <h3 className="card-title">个人使用情况</h3>
  </div>
  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
    <UsageRow label="本周工具使用" value={stats ? `${stats.week_tool_count} 次` : '—'} />
    <UsageRow
      label="最近使用工具"
      value={stats?.recent_tools?.[0]?.tool_name ?? '—'}
    />
    <UsageRow
      label="最近登录"
      value={stats?.last_login_at
        ? new Date(stats.last_login_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
        : '—'}
    />
  </div>
</div>
```

**UsageRow 内联组件：**

```tsx
function UsageRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-800)' }}>{value}</span>
    </div>
  )
}
```

---

### 3.5 底部行 — 保留现有最近任务 + 最近产出

布局和内容与现有完全相同，无需改动。

---

## 四、完整页面结构

```tsx
return (
  <>
    {/* 顶部欢迎区 */}
    <div className="page-header"> ... </div>

    {/* 工作概览 - 4 卡片 */}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
      ...
    </div>

    {/* 趋势图 + 个人使用情况 */}
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
      ...
    </div>

    {/* 最近任务 + 最近产出（现有保留） */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-4)' }}>
      ...
    </div>
  </>
)
```

---

## 五、注意事项

1. **图表库确认**：先查 `package.json` 再决定用哪个，不要默认安装
2. **loading 状态**：统计数据加载中时，卡片数字区域显示占位灰条，不显示 0
3. **null 处理**：`week_token_usage` 可能为 null（后端未追踪），显示「—」不报错
4. `last_login_at` 可能为 null，显示「—」
5. **不改动**现有最近任务 / 最近产出逻辑

---

## 六、验收标准

1. 4 张统计卡片数字与后端接口返回一致
2. 折线图展示7个点，无数据日期点显示 0（不断线）
3. 个人使用情况3行信息正常展示，null 时显示「—」
4. 页面加载时统计区有 loading 状态，不直接显示 0
5. 底部最近任务 / 最近产出功能不受影响
