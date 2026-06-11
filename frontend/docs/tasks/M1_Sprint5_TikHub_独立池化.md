# MCN_Frontend_Agent — M1 Sprint 5 任务指令（TikHub 配置页面重构）

> 角色：MCN_Frontend_Agent（前端开发 Claude）
> 工作目录：`frontend/`
> PM 生成时间：2026-06-10
> 前置条件：M1 Sprint 2 TikHub 基础抓取功能已运行
> 完成后：回传 PM，等待后端联调

---

## M1 Sprint 5 目标

将 TikHub 配置页面重构为与 AI 配置页面相同的布局结构，实现：
1. 统计卡片区域
2. 图表区域
3. 过滤器区域
4. Key 列表（显示并发、调用统计、延迟）
5. 接口统计表格
6. 用户调用排行表格

---

## 一、页面布局结构

### 1.1 参考 AI 配置页面（AiConfigTab）

**文件：** `frontend/src/pages/admin/ServiceConfigPage.tsx`

**AI 配置页面结构（200-712 行）：**
1. 统计卡片区域（4 个卡片）
2. 图表区域（环形图 + 折线图）
3. 过滤器区域（状态筛选 + 搜索框）
4. Key 列表（KeyRow 组件）
5. 模型管理表格

### 1.2 TikHub 配置页面目标结构

1. **统计卡片区域**（5 个卡片）
   - 总调用量
   - 今日调用量
   - 平均延迟
   - 活跃 Key 数
   - 总 Key 数

2. **图表区域**（2 个图表）
   - 接口占比环形图（DonutChart）
   - 7 日调用趋势折线图（LineChart）

3. **过滤器区域**
   - 状态筛选（全部/启用/停用）
   - 搜索框（按 label 搜索）

4. **Key 列表区域**（每个 Key 显示）
   - 标签
   - API Key（可显示/隐藏）
   - Base URL
   - 状态标签
   - 并发情况（2 / 5）
   - 最大并发
   - 今日调用次数
   - 总调用次数
   - 最后测试时间
   - 最后延迟
   - 操作按钮（测试/编辑/启用或停用/删除）

5. **接口统计表格**
   - 接口名称
   - 调用次数
   - 占比
   - 平均延迟
   - 成功率

6. **用户调用排行表格**
   - 用户名
   - 调用次数
   - 最后调用时间

---

## 二、接口调用

### 2.1 新增 API 函数

**文件：** `frontend/src/services/api.ts`

```typescript
// TikHub 统计
export async function getTikHubStats(params?: {
  start_date?: string;
  end_date?: string;
}): Promise<TikHubStatsResponse> {
  return request.get('/admin/tikhub/stats', { params });
}

// TikHub Key 列表
export async function getTikHubKeys(params?: {
  status?: string;
  search?: string;
}): Promise<PagedData<TikHubKey>> {
  return request.get('/admin/tikhub/keys', { params });
}

// 新增 TikHub Key
export async function createTikHubKey(data: CreateTikHubKeyRequest): Promise<TikHubKey> {
  return request.post('/admin/tikhub/keys', data);
}

// 编辑 TikHub Key
export async function updateTikHubKey(id: number, data: UpdateTikHubKeyRequest): Promise<TikHubKey> {
  return request.put(`/admin/tikhub/keys/${id}`, data);
}

// 删除 TikHub Key
export async function deleteTikHubKey(id: number): Promise<void> {
  return request.delete(`/admin/tikhub/keys/${id}`);
}

// 测试 TikHub Key
export async function testTikHubKey(id: number): Promise<TestResult> {
  return request.post(`/admin/tikhub/keys/${id}/test`);
}

// 启用 TikHub Key
export async function enableTikHubKey(id: number): Promise<void> {
  return request.post(`/admin/tikhub/keys/${id}/enable`);
}

// 停用 TikHub Key
export async function disableTikHubKey(id: number): Promise<void> {
  return request.post(`/admin/tikhub/keys/${id}/disable`);
}

// TikHub 接口统计
export async function getTikHubEndpoints(): Promise<TikHubEndpoint[]> {
  return request.get('/admin/tikhub/endpoints');
}

// TikHub 用户调用排行
export async function getTikHubUsers(params?: {
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<PagedData<TikHubUserRank>> {
  return request.get('/admin/tikhub/users', { params });
}
```

### 2.2 TypeScript 类型定义

**文件：** `frontend/src/types/api.ts`

```typescript
// TikHub 统计响应
export interface TikHubStatsResponse {
  overview: {
    total_calls: number;
    today_calls: number;
    avg_latency_ms: number;
    active_keys: number;
    total_keys: number;
  };
  endpoints: Array<{
    endpoint: string;
    calls: number;
    percentage: number;  // 0-100
  }>;
  users: Array<{
    user_id: number;
    username: string;
    calls: number;
  }>;
  trend: Array<{
    date: string;  // "06-04"
    calls: number;
  }>;
}

// TikHub Key 记录
export interface TikHubKey {
  id: number;
  label: string;
  api_key: string;
  base_url: string;
  status: 'active' | 'inactive';
  active_requests: number;
  max_concurrent: number;
  today_calls: number;
  total_calls: number;
  last_tested_at: string | null;
  last_latency_ms: number | null;
  created_at: string;
}

// 创建 TikHub Key 请求
export interface CreateTikHubKeyRequest {
  label: string;
  api_key: string;
  base_url: string;
  max_concurrent: number;
  max_users: number;
}

// 更新 TikHub Key 请求
export interface UpdateTikHubKeyRequest {
  label?: string;
  max_concurrent?: number;
  max_users?: number;
}

// 测试结果
export interface TestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  sample_nickname?: string;
  error?: string;
}

// TikHub 接口统计
export interface TikHubEndpoint {
  endpoint: string;
  platform: string;
  calls: number;
  percentage: number;  // 0-100
  avg_latency_ms: number;
  success_rate: number;  // 0-1
}

// TikHub 用户调用排行
export interface TikHubUserRank {
  user_id: number;
  username: string;
  role: string;
  calls: number;
  last_called_at: string;
}
```

---

## 三、组件实现

### 3.1 TikHubConfigTab 组件

**文件：** `frontend/src/pages/admin/ServiceConfigPage.tsx`

**位置：** 在 `AiConfigTab` 组件后添加新的 `TikHubConfigTab` 组件

**核心逻辑：**

```typescript
function TikHubConfigTab() {
  const [stats, setStats] = useState<TikHubStatsResponse | null>(null);
  const [keys, setKeys] = useState<PagedData<TikHubKey> | null>(null);
  const [endpoints, setEndpoints] = useState<TikHubEndpoint[]>([]);
  const [users, setUsers] = useState<PagedData<TikHubUserRank> | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [searchText, setSearchText] = useState('');

  // 加载统计数据
  useEffect(() => {
    setLoading(true);
    getTikHubStats()
      .then(setStats)
      .catch(() => message.error('加载统计数据失败'))
      .finally(() => setLoading(false));
  }, []);

  // 加载 Key 列表
  useEffect(() => {
    getTikHubKeys({ status: statusFilter, search: searchText })
      .then(setKeys)
      .catch(() => message.error('加载 Key 列表失败'));
  }, [statusFilter, searchText]);

  // 加载接口统计
  useEffect(() => {
    getTikHubEndpoints()
      .then(setEndpoints)
      .catch(() => message.error('加载接口统计失败'));
  }, []);

  // 加载用户排行
  useEffect(() => {
    getTikHubUsers({ limit: 20 })
      .then(setUsers)
      .catch(() => message.error('加载用户排行失败'));
  }, []);

  // ... 渲染逻辑
}
```

### 3.2 统计卡片区域

```tsx
<div className="stats-grid">
  <div className="stat-card">
    <div className="stat-label">总调用量</div>
    <div className="stat-value">{stats?.overview.total_calls.toLocaleString() || 0}</div>
  </div>
  <div className="stat-card">
    <div className="stat-label">今日调用量</div>
    <div className="stat-value">{stats?.overview.today_calls.toLocaleString() || 0}</div>
  </div>
  <div className="stat-card">
    <div className="stat-label">平均延迟</div>
    <div className="stat-value">{stats?.overview.avg_latency_ms.toFixed(0) || 0}ms</div>
  </div>
  <div className="stat-card">
    <div className="stat-label">活跃 Key</div>
    <div className="stat-value">{stats?.overview.active_keys || 0}</div>
  </div>
  <div className="stat-card">
    <div className="stat-label">总 Key 数</div>
    <div className="stat-value">{stats?.overview.total_keys || 0}</div>
  </div>
</div>
```

### 3.3 图表区域

复用 AI 配置页面的 `DonutChart` 和 `LineChart` 组件：

```tsx
<div className="charts-row">
  <div className="chart-card">
    <h3>接口占比</h3>
    <DonutChart
      data={stats?.endpoints.map(e => ({ label: e.endpoint, value: e.calls, pct: e.percentage })) || []}
      size={180}
    />
  </div>
  <div className="chart-card">
    <h3>7 日调用趋势</h3>
    <LineChart
      data={stats?.trend.map(t => ({ date: t.date, value: t.calls })) || []}
      height={180}
    />
  </div>
</div>
```

### 3.4 过滤器区域

```tsx
<div className="filter-bar">
  <Select
    value={statusFilter}
    onChange={setStatusFilter}
    style={{ width: 120 }}
    options={[
      { label: '全部', value: '' },
      { label: '启用', value: 'active' },
      { label: '停用', value: 'inactive' },
    ]}
  />
  <Input
    placeholder="搜索 Key 标签"
    value={searchText}
    onChange={e => setSearchText(e.target.value)}
    style={{ width: 200 }}
  />
</div>
```

### 3.5 Key 列表区域

复用 `KeyRow` 组件，调整为 TikHub 字段：

```tsx
{keys?.items.map(key => (
  <TikHubKeyRow
    key={key.id}
    data={key}
    onTest={handleTest}
    onEdit={handleEdit}
    onToggle={handleToggle}
    onDelete={handleDelete}
  />
))}
```

**TikHubKeyRow 组件：**

```typescript
function TikHubKeyRow({ data, onTest, onEdit, onToggle, onDelete }: TikHubKeyRowProps) {
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await testTikHubKey(data.id);
      if (result.status === 'ok') {
        message.success(`正常，延迟 ${result.latency_ms}ms`);
      } else {
        message.error(`失败：${result.error || '未知'}`);
      }
    } catch {
      message.error('测试失败');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="key-row">
      <div>
        <div className="key-label">{data.label}</div>
        <div className="key-tail">
          {showKey ? data.api_key : `···· ${data.api_key.slice(-4)}`}
        </div>
      </div>
      <div style={{ color: 'var(--gray-500)', fontSize: 12 }}>{data.base_url}</div>
      <div>
        <span className={`badge ${data.status === 'active' ? 'badge-success' : 'badge-gray'}`}>
          {data.status === 'active' ? '启用' : '停用'}
        </span>
      </div>
      <div>
        {data.active_requests} / {data.max_concurrent}
      </div>
      <div>{data.today_calls.toLocaleString()}</div>
      <div>{data.total_calls.toLocaleString()}</div>
      <div style={{ color: 'var(--gray-400)', fontSize: 12 }}>
        {data.last_tested_at ? new Date(data.last_tested_at).toLocaleString() : '—'}
      </div>
      <div style={{ color: 'var(--gray-400)', fontSize: 12 }}>
        {data.last_latency_ms ? `${data.last_latency_ms}ms` : '—'}
      </div>
      <div />
      <div className="key-actions">
        <button className="btn btn-ghost btn-sm" disabled={testing} onClick={handleTest}>
          {testing ? '测试...' : '测试'}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={() => onEdit(data)}>编辑</button>
        <Popconfirm
          title={data.status === 'active' ? '确认停用？' : '确认启用？'}
          onConfirm={() => onToggle(data)}
        >
          <button className="btn btn-ghost btn-sm">
            {data.status === 'active' ? '停用' : '启用'}
          </button>
        </Popconfirm>
        <Popconfirm title="确认删除该 Key？" onConfirm={() => onDelete(data.id)}>
          <button className="btn btn-danger-ghost btn-sm">删除</button>
        </Popconfirm>
      </div>
    </div>
  );
}
```

### 3.6 接口统计表格

```tsx
<div className="table-section">
  <h3>接口统计</h3>
  <table className="data-table">
    <thead>
      <tr>
        <th>接口名称</th>
        <th>平台</th>
        <th>调用次数</th>
        <th>占比</th>
        <th>平均延迟</th>
        <th>成功率</th>
      </tr>
    </thead>
    <tbody>
      {endpoints.map(ep => (
        <tr key={ep.endpoint}>
          <td>{ep.endpoint}</td>
          <td>{ep.platform}</td>
          <td>{ep.calls.toLocaleString()}</td>
          <td>{ep.percentage.toFixed(1)}%</td>
          <td>{ep.avg_latency_ms.toFixed(0)}ms</td>
          <td>{(ep.success_rate * 100).toFixed(1)}%</td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

### 3.7 用户调用排行表格

```tsx
<div className="table-section">
  <h3>用户调用排行（Top 20）</h3>
  <table className="data-table">
    <thead>
      <tr>
        <th>用户名</th>
        <th>角色</th>
        <th>调用次数</th>
        <th>最后调用时间</th>
      </tr>
    </thead>
    <tbody>
      {users?.items.map(user => (
        <tr key={user.user_id}>
          <td>{user.username}</td>
          <td>{user.role}</td>
          <td>{user.calls.toLocaleString()}</td>
          <td>{new Date(user.last_called_at).toLocaleString()}</td>
        </tr>
      ))}
    </tbody>
  </table>
</div>
```

---

## 四、Modals（新增/编辑 Key）

参考 AI 配置页面的 Modal 实现：

### 4.1 新增 Key Modal

```tsx
<Modal
  title="新增 TikHub Key"
  open={createOpen}
  onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
  onOk={() => createForm.submit()}
  okText="创建"
  cancelText="取消"
  confirmLoading={formLoading}
>
  <Form form={createForm} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
    <Form.Item label="标签" name="label" rules={[{ required: true, message: '请输入标签' }]}>
      <Input placeholder="如 tikhub-main" />
    </Form.Item>
    <Form.Item label="API Key" name="api_key" rules={[{ required: true, message: '请输入 API Key' }]}>
      <Input.Password />
    </Form.Item>
    <Form.Item label="Base URL" name="base_url" initialValue="https://api.tikhub.io">
      <Input />
    </Form.Item>
    <Form.Item label="最大并发数" name="max_concurrent" initialValue={5}>
      <Input type="number" />
    </Form.Item>
    <Form.Item label="最大用户数" name="max_users" initialValue={10}>
      <Input type="number" />
    </Form.Item>
  </Form>
</Modal>
```

### 4.2 编辑 Key Modal

```tsx
<Modal
  title="编辑 TikHub Key"
  open={!!editKey}
  onCancel={() => setEditKey(null)}
  onOk={() => editForm.submit()}
  okText="保存"
  cancelText="取消"
  confirmLoading={formLoading}
>
  <Form form={editForm} layout="vertical" onFinish={handleUpdate} style={{ marginTop: 16 }}>
    <Form.Item label="标签" name="label" rules={[{ required: true, message: '请输入标签' }]}>
      <Input />
    </Form.Item>
    <Form.Item label="最大并发数" name="max_concurrent">
      <Input type="number" />
    </Form.Item>
    <Form.Item label="最大用户数" name="max_users">
      <Input type="number" />
    </Form.Item>
  </Form>
</Modal>
```

---

## 五、ServiceConfigPage 主组件调整

### 5.1 修改 Tabs 渲染逻辑

**位置：** `ServiceConfigPage` 组件，`provider === 'tikhub'` 时渲染 `TikHubConfigTab`

```typescript
{/* AI tab content */}
{provider === 'ai' && <AiConfigTab />}

{/* TikHub tab content */}
{provider === 'tikhub' && <TikHubConfigTab />}

{/* Non-AI/Non-TikHub content stays inside the card */}
{provider !== 'ai' && provider !== 'tikhub' && (
  // ... 原有的 OSS/ASR 简单列表展示
)}
```

### 5.2 移除 TikHub 的"新增 Key"按钮

TikHub 的新增 Key 按钮应该放在 `TikHubConfigTab` 组件内部，不在页面顶部：

```tsx
{provider !== 'ai' && provider !== 'tikhub' && (
  <div className="page-actions">
    <button className="btn btn-primary" onClick={openCreate}>+ 新增 Key</button>
  </div>
)}
```

---

## 六、样式调整

### 6.1 复用现有样式

TikHub 配置页面复用 AI 配置页面的所有样式类：
- `.stats-grid` / `.stat-card` / `.stat-label` / `.stat-value`
- `.charts-row` / `.chart-card`
- `.filter-bar`
- `.key-row` / `.key-label` / `.key-tail` / `.key-actions`
- `.badge` / `.badge-success` / `.badge-gray`
- `.table-section` / `.data-table`

### 6.2 统计卡片数量调整

AI 配置页面是 4 个统计卡片，TikHub 是 5 个，需要调整 CSS Grid：

```css
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);  /* 改为 5 列 */
  gap: 16px;
  margin-bottom: 24px;
}
```

或者保持 4 列，将第 5 个卡片换行：

```css
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
```

---

## 七、测试验证

### 7.1 功能测试
- ✅ 统计卡片正确显示数据
- ✅ 图表正确渲染（环形图 + 折线图）
- ✅ 状态筛选和搜索功能正常
- ✅ Key 列表正确显示所有字段
- ✅ 测试按钮返回正确结果
- ✅ 新增/编辑/删除 Key 功能正常
- ✅ 启用/停用 Key 功能正常
- ✅ 接口统计表格正确显示
- ✅ 用户排行表格正确显示

### 7.2 样式测试
- ✅ 页面布局与 AI 配置页面一致
- ✅ 统计卡片、图表、表格样式统一
- ✅ 响应式布局正常

### 7.3 边界测试
- ✅ 无数据时显示"暂无数据"
- ✅ 加载中显示 Loading 状态
- ✅ 错误时显示错误提示

---

## 八、回传 PM 内容

完成后回传以下信息：

1. ✅ TikHubConfigTab 组件已实现
2. ✅ 统计卡片、图表、过滤器、列表、表格全部完成
3. ✅ 新增/编辑/删除功能正常
4. ✅ 样式与 AI 配置页面一致
5. ✅ 测试验证通过

并告知：
- 是否遇到样式不统一的问题
- 是否需要调整图表数据格式
- Key 列表的列显示是否需要调整

---

**PM 备注：**
- 字段名必须与后端接口返回的字段名完全一致
- 百分比字段是 0-100 范围（不是 0-1）
- 时间字段统一使用 ISO 8601 格式
- 复用 AI 配置页面的所有样式和组件
- 只重构 TikHub 配置，OSS/ASR 保持原有简单列表
