# 前端任务单 · kol-intake 整合进「功能管理」

> 目标：将「红人信息采集助手」的管理入口从侧边栏独立菜单移入「功能管理」页面，
> 侧边栏不再单独显示该菜单项。
>
> 涉及文件：
> - `src/layouts/AdminLayout.tsx`
> - `src/pages/admin/WorkspaceConfigPage.tsx`
>
> 不需要改动：`AdminIntakePage.tsx`（保留组件文件，但不再单独渲染）

---

## 改动 1 — AdminLayout：删除「入驻问卷」菜单项

**文件**：`src/layouts/AdminLayout.tsx`

从 GROUPS 里删掉「入驻问卷」这一条，同时把「功能管理」改名为「工具配置」（语义更准确）：

**改前：**
```ts
const GROUPS: NavGroup[] = [
  {
    title: '功能管理',
    items: [
      { path: '/admin',           label: '仪表盘' },
      { path: '/admin/users',     label: '用户管理' },
      { path: '/admin/kols',      label: '红人管理' },
      { path: '/admin/intake',    label: '入驻问卷' },   // ← 删除
      { path: '/admin/workspace', label: '功能管理' },
      { path: '/admin/tasks',     label: '产品管理' },
      { path: '/admin/outputs',   label: '用户产出' },
    ],
  },
  ...
```

**改后：**
```ts
const GROUPS: NavGroup[] = [
  {
    title: '功能管理',
    items: [
      { path: '/admin',           label: '仪表盘' },
      { path: '/admin/users',     label: '用户管理' },
      { path: '/admin/kols',      label: '红人管理' },
      { path: '/admin/workspace', label: '工具配置' },   // ← 改名
      { path: '/admin/tasks',     label: '产品管理' },
      { path: '/admin/outputs',   label: '用户产出' },
    ],
  },
  ...
```

---

## 改动 2 — WorkspaceConfigPage：改为双 Tab 布局

**文件**：`src/pages/admin/WorkspaceConfigPage.tsx`

### 2.1 整体结构

页面顶部加 Ant Design `Tabs`，两个 Tab：

| Tab key | Tab 标题 | 内容 |
|---------|----------|------|
| `tools` | 工具列表 | 现有 WorkspaceConfigPage 全部内容（不改） |
| `intake` | 红人信息采集助手 | 直接渲染 `<AdminIntakePage />` |

### 2.2 改动代码

在文件顶部补 import：

```tsx
import { Tabs } from 'antd';
import AdminIntakePage from './AdminIntakePage';
```

原来 `return (...)` 整体改为：

```tsx
return (
  <>
    <div className="page-header">
      <div>
        <h1 className="page-title">工具配置</h1>
        <p className="page-desc">管理内容工作台工具及 AI 功能配置</p>
      </div>
    </div>

    <Tabs
      defaultActiveKey="tools"
      items={[
        {
          key: 'tools',
          label: '工具列表',
          children: (
            <>
              {/* 原有工具列表全部内容，原样保留，page-header 去掉（已移到外层） */}
              <div className="card">
                <div className="filter-bar">
                  <span className="filter-count">共 {tools.length} 个工具</span>
                </div>
                {loading
                  ? <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
                  : tools.length === 0
                    ? <div className="empty-state"><div className="empty-state-text">暂无工具配置</div></div>
                    : (
                      <table className="ant-table">
                        <thead>
                          <tr>
                            <th>工具代码</th>
                            <th>工具名称</th>
                            <th>分类</th>
                            <th>状态</th>
                            <th>描述</th>
                            <th className="col-actions">操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tools.map(t => (
                            <tr key={t.tool_code}>
                              <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--gray-400)' }}>{t.tool_code}</td>
                              <td style={{ fontWeight: 600 }}>{t.tool_name}</td>
                              <td><span className="badge badge-brand">{t.category}</span></td>
                              <td><span className={`badge ${sClass(t.status)}`}>{sLabel(t.status)}</span></td>
                              <td style={{ color: 'var(--gray-500)', fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.description}</td>
                              <td className="col-actions">
                                <button className="btn btn-ghost btn-sm" onClick={() => {
                                  setEditTool(t);
                                  form.setFieldsValue({ tool_name: t.tool_name, description: t.description, category: t.category, status: t.status, sort_order: t.sort_order });
                                }}>编辑</button>
                                <Popconfirm title={t.status === 'online' ? '确认停用？' : '确认启用？'} okText="确认" cancelText="取消" onConfirm={() => handleToggle(t)}>
                                  <button className="btn btn-ghost btn-sm">{t.status === 'online' ? '停用' : '启用'}</button>
                                </Popconfirm>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )
                }
              </div>

              {/* 编辑弹窗，原样保留 */}
              <Modal title={`编辑：${editTool?.tool_name ?? ''}`} open={!!editTool} onCancel={() => setEditTool(null)} onOk={() => form.submit()} okText="保存" confirmLoading={formLoading}>
                <Form form={form} layout="vertical" onFinish={handleUpdate} style={{ marginTop: 16 }}>
                  <Form.Item label="工具名称" name="tool_name" rules={[{ required: true }]}><Input /></Form.Item>
                  <Form.Item label="分类" name="category" rules={[{ required: true }]}><Input /></Form.Item>
                  <Form.Item label="描述" name="description"><Input.TextArea rows={3} /></Form.Item>
                  <Form.Item label="状态" name="status">
                    <Select>
                      <Select.Option value="online">在线</Select.Option>
                      <Select.Option value="dev">开发中</Select.Option>
                      <Select.Option value="offline">下线</Select.Option>
                      <Select.Option value="disabled">停用</Select.Option>
                    </Select>
                  </Form.Item>
                  <Form.Item label="排序" name="sort_order"><Input type="number" /></Form.Item>
                </Form>
              </Modal>
            </>
          ),
        },
        {
          key: 'intake',
          label: '红人信息采集助手',
          children: <AdminIntakePage />,
        },
      ]}
    />
  </>
);
```

---

## 改动 3 — AdminIntakePage：隐藏内部 page-header

**文件**：`src/pages/admin/AdminIntakePage.tsx`

`AdminIntakePage` 当作子组件嵌入后，它自己的 `page-header`（「入驻问卷配置」标题和描述）与外层 `WorkspaceConfigPage` 的标题重叠，需要隐藏。

方式：加一个 `embedded` prop，`true` 时不渲染 `page-header`：

```tsx
// 函数签名加 prop
export default function AdminIntakePage({ embedded = false }: { embedded?: boolean }) {

  // ...（逻辑不变）

  return (
    <>
      {!embedded && (          // ← 用 embedded 控制
        <div className="page-header">
          <div>
            <h1 className="page-title">入驻问卷配置</h1>
            <p className="page-desc">管理 AI 对话模型、系统提示词和题目提纲</p>
          </div>
        </div>
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[...]} />
      {/* 其余内容不变 */}
    </>
  );
}
```

在 `WorkspaceConfigPage` 里引用时传 `embedded`：

```tsx
children: <AdminIntakePage embedded />,
```

`/admin/intake` 路由直接渲染时不传 prop，保持原来的独立页面样式（路由保留，万一有人直接访问不会白屏）。

---

## 改动汇总

| # | 文件 | 改动 |
|---|------|------|
| 1 | `AdminLayout.tsx` | 删「入驻问卷」菜单项；「功能管理」label 改为「工具配置」 |
| 2 | `WorkspaceConfigPage.tsx` | 改为 Tabs 布局，新增「红人信息采集助手」Tab 嵌入 AdminIntakePage |
| 3 | `AdminIntakePage.tsx` | 加 `embedded` prop，嵌入时隐藏 page-header |

**改动量**：约 30 行净改，无新依赖，TypeScript 零新 `any`。
