# MCN_Frontend_Agent — M2 Sprint 2 补充任务（运营端首页页面还原）

> 角色：MCN_Frontend_Agent（前端开发 Claude）  
> 工作目录：`frontend/`  
> PM 生成时间：2026-06-08  
> 前置条件：后端 M2 Sprint 2 补充接口已就绪  
> 设计稿参考：`C:\Users\15032\Downloads\ChatGPT Image 2026年6月8日 14_29_55.png`  
> 完成后：回传 PM

---

## 背景

在原有 M2 Sprint 2 前端任务基础上，根据设计稿评审补充以下内容：

1. 统计卡片补充同比变化率
2. 右侧图表改为工具使用占比环形图
3. 底部新增「常用工具」快捷入口区（6 个）

---

## 一、类型定义更新（`src/api/homepage.ts`）

在原有 `HomepageStats` 类型中补充字段：

```typescript
export interface HomepageStats {
  today_outputs: number
  today_outputs_change: string | null       // 新增："+40.0%" / "-5.0%" / null
  week_outputs: number
  week_outputs_change: string | null        // 新增："+17.4%" / null
  in_progress_tasks: number
  week_token_usage: number | null
  week_tool_count: number
  tool_usage_breakdown: {                   // 新增：饼图数据
    tool_name: string
    tool_code: string | null
    count: number
    percentage: number
  }[]
  recent_tools: {
    tool_name: string
    tool_code: string
    last_used_at: string
  }[]                                       // 数量从 3 扩展到 6
  last_login_at: string | null
}
```

---

## 二、统计卡片补充变化率

**设计稿对应区域：** 顶部 4 张卡片，每张卡片下方有绿色/红色百分比

修改 `StatCard` 组件，增加 `change` 属性：

```tsx
function StatCard({ label, value, unit, sub, change, loading }: {
  label: string
  value: string | number
  unit?: string
  sub?: string
  change?: string | null   // 新增：变化率，如 "+40.0%" / "-5.0%"
  loading?: boolean
}) {
  const changeColor = change?.startsWith('+') ? '#52c41a' : '#ff4d4f'
  return (
    <div className="card" style={{ padding: 'var(--sp-4)' }}>
      <div style={{ color: 'var(--gray-500)', fontSize: 13, marginBottom: 8 }}>{label}</div>
      {loading
        ? <div style={{ height: 32, background: 'var(--gray-100)', borderRadius: 4 }} />
        : <>
            <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--gray-900)', lineHeight: 1.2 }}>
              {value}<span style={{ fontSize: 13, color: 'var(--gray-500)', marginLeft: 4 }}>{unit}</span>
            </div>
            {change != null && (
              <div style={{ fontSize: 12, color: changeColor, marginTop: 4 }}>
                {change} 较{sub ?? '昨日'}
              </div>
            )}
            {change == null && sub && (
              <div style={{ fontSize: 12, color: 'var(--gray-400)', marginTop: 4 }}>{sub}</div>
            )}
          </>
      }
    </div>
  )
}
```

**调用处更新：**

```tsx
<StatCard label="今日产出"   value={stats?.today_outputs ?? 0}  unit="篇" change={stats?.today_outputs_change}  sub="昨日" loading={statsLoading} />
<StatCard label="本周产出"   value={stats?.week_outputs ?? 0}   unit="篇" change={stats?.week_outputs_change}   sub="上周" loading={statsLoading} />
<StatCard label="进行中任务" value={stats?.in_progress_tasks ?? 0} unit="个" sub="实时" loading={statsLoading} />
<StatCard
  label="Token 消耗"
  value={stats?.week_token_usage != null ? formatToken(stats.week_token_usage) : '—'}
  sub="本周"
  loading={statsLoading}
/>
```

---

## 三、中间行右侧改为工具使用占比环形图

**设计稿对应区域：** 右侧卡片，环形图中心显示本周总使用次数，外圈显示各工具占比

**原设计为「个人使用情况」文字列表，根据设计稿改为两个独立卡片：**

### 中间行布局调整

```
左（2fr）：内容产出趋势折线图（不变）
右（1fr）：拆为上下两块
  - 上：工具使用占比环形图
  - 下：个人使用情况文字（本周使用次数 / 最近登录）
```

或直接参考设计稿，右侧只放环形图卡片，「最近登录」信息移入欢迎区右侧。**以设计稿为准。**

### 环形图实现

**优先查看 `package.json`：**
- 有 `recharts` → 使用 `PieChart` + `Pie` + `Cell`
- 有 `@ant-design/charts` → 使用 `Donut` 组件
- 都没有 → 安装 `recharts`

**recharts 实现参考：**

```tsx
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const COLORS = ['#4F6EF7', '#36CFC9', '#FFA940', '#FF7875', '#D9D9D9']

function ToolUsageChart({ data, total, loading }: {
  data: HomepageStats['tool_usage_breakdown']
  total: number
  loading: boolean
}) {
  if (loading) return <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
  if (!data.length) return <div className="empty-state"><div className="empty-state-text">本周暂无工具使用记录</div></div>
  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">工具使用占比</h3>
        <span style={{ fontSize: 12, color: 'var(--gray-400)' }}>本周</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
        {/* 环形图 */}
        <div style={{ position: 'relative', width: 140, height: 140, flexShrink: 0 }}>
          <ResponsiveContainer width={140} height={140}>
            <PieChart>
              <Pie data={data} cx={65} cy={65} innerRadius={45} outerRadius={65}
                   dataKey="percentage" paddingAngle={2}>
                {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
            </PieChart>
          </ResponsiveContainer>
          {/* 中心文字 */}
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--gray-900)' }}>{total}</div>
            <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>次</div>
          </div>
        </div>
        {/* 图例 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
          {data.map((item, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: COLORS[i % COLORS.length], flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: 'var(--gray-600)' }}>{item.tool_name}</span>
              </div>
              <span style={{ fontSize: 12, color: 'var(--gray-500)' }}>{item.percentage.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

**调用处：**
```tsx
<ToolUsageChart
  data={stats?.tool_usage_breakdown ?? []}
  total={stats?.week_tool_count ?? 0}
  loading={statsLoading}
/>
```

---

## 四、新增「常用工具」快捷入口区

**设计稿对应区域：** 底部左侧，工具卡片网格，展示最近使用的 6 个工具

位置：插入在「最近任务 / 最近产出」行的**上方**

```tsx
{/* 常用工具 */}
{stats?.recent_tools && stats.recent_tools.length > 0 && (
  <div className="card" style={{ marginBottom: 'var(--sp-4)' }}>
    <div className="card-header">
      <h3 className="card-title">常用工具</h3>
      <button className="btn btn-ghost btn-sm" onClick={() => navigate('/workspace')}>更多工具</button>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--sp-3)' }}>
      {stats.recent_tools.map(tool => (
        <button
          key={tool.tool_code}
          className="btn btn-ghost"
          style={{ justifyContent: 'flex-start', padding: 'var(--sp-3)', height: 'auto', textAlign: 'left' }}
          onClick={() => navigate(`/workspace/${tool.tool_code}`)}
        >
          <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-800)', marginBottom: 2 }}>
            {tool.tool_name}
          </div>
          <div style={{ fontSize: 11, color: 'var(--gray-400)' }}>
            {new Date(tool.last_used_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })}
          </div>
        </button>
      ))}
    </div>
  </div>
)}
```

---

## 五、完整页面布局顺序（最终）

```tsx
return (
  <>
    {/* 1. 顶部欢迎区 */}
    <div className="page-header"> ... </div>

    {/* 2. 工作概览 - 4 卡片（含变化率） */}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
      ...
    </div>

    {/* 3. 内容趋势（左）+ 工具使用占比（右） */}
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}>
      {/* 折线图卡片（不变） */}
      {/* 环形图卡片（新） */}
    </div>

    {/* 4. 常用工具（新增） */}
    ...

    {/* 5. 最近任务 + 最近产出（现有保留） */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-4)' }}>
      ...
    </div>
  </>
)
```

---

## 六、验收标准

| 检查项 | 预期结果 |
|--------|---------|
| 统计卡片变化率 | 正数绿色，负数红色，null 不显示 |
| 工具使用环形图 | 中心显示总次数，外圈各工具占比，图例对齐设计稿颜色 |
| 环形图无数据 | 显示「本周暂无工具使用记录」 |
| 常用工具 6 个 | 点击跳转 `/workspace/{tool_code}` |
| 常用工具无数据 | 整个区块不显示 |
| 页面整体与设计稿对齐 | 参考 `C:\Users\15032\Downloads\ChatGPT Image 2026年6月8日 14_29_55.png` |
