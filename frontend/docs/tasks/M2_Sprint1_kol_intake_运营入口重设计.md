# 前端任务单 · kol-intake 运营端入口重设计

> 目标：将「红人信息采集助手」运营页面从「链接管理表格」改为支持两个场景的入口页面：
>
> - **场景 A（面对面）**：运营和红人在一起，运营直接点「开始采集」→ 系统自动创建链接 → 当前页跳转到 `/intake/:token`
> - **场景 B（远程）**：运营和红人不在一起，点「创建分享链接」→ 弹窗设置有效期和姓名 → 复制链接发给红人
>
> 涉及文件：`src/pages/operator/OperatorIntakePage.tsx`
>
> 不涉及：`App.tsx` 路由、API、类型均不改动

---

## 页面结构

```
┌─────────────────────────────────────────────────────┐
│ 红人信息采集助手                                     │
│ 面对面采集或生成链接远程邀请红人完成 AI 对话          │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │   🎙 面对面采集       │  │  🔗 远程分享链接    │  │
│  │                      │  │                     │  │
│  │  运营和红人在一起时   │  │  红人自己扫码/点链接 │  │
│  │  直接开始 AI 对话     │  │  完成 AI 对话采集   │  │
│  │                      │  │                     │  │
│  │  [填写红人姓名（选填）]│  │  [创建分享链接]     │  │
│  │  [开始采集 →]        │  │                     │  │
│  └──────────────────────┘  └─────────────────────┘  │
│                                                     │
│  ── 历史链接 ──────────────────────────────────────  │
│  ┌──────────┬──────┬──────┬──────┬──────┬────────┐  │
│  │ 红人姓名 │ 状态 │ 到期 │ 访问 │ 提交 │ 操作   │  │
│  └──────────┴──────┴──────┴──────┴──────┴────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 改动详情

### 1. import 补充

```tsx
import { useNavigate } from 'react-router-dom';
```

（`createIntakeLink`、`getIntakeLinks` 等已有，不变）

### 2. state 调整

```tsx
const navigate = useNavigate();

// 新增：面对面采集表单
const [directKolName, setDirectKolName] = useState('');
const [directLoading, setDirectLoading] = useState(false);

// 保留原有：
// const [showCreate, setShowCreate] = useState(false);  ← 用于「创建分享链接」弹窗
// const [links, setLinks] = useState<IntakeLink[]>([]);
// const [loading, setLoading] = useState(false);
// const [form] = Form.useForm();
```

### 3. 新增「直接开始」处理函数

```tsx
async function handleDirectStart() {
  setDirectLoading(true);
  try {
    const res = await createIntakeLink({
      kol_name: directKolName.trim() || undefined,
      expire_hours: 2,   // 面对面场景默认 2 小时，够用即可
    });
    navigate(`/intake/${res.token}`);
  } catch (err: unknown) {
    message.error((err as Error).message || '创建失败，请重试');
  } finally {
    setDirectLoading(false);
  }
}
```

### 4. return 整体替换

```tsx
return (
  <>
    <div className="page-header">
      <div>
        <h1 className="page-title">红人信息采集助手</h1>
        <p className="page-desc">面对面采集或生成链接远程邀请红人完成 AI 对话</p>
      </div>
    </div>

    {/* ── 两个入口卡片 ── */}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 32 }}>

      {/* 卡片 A：面对面采集 */}
      <div className="card" style={{ padding: '24px 28px' }}>
        <div style={{ fontSize: 28, marginBottom: 12 }}>🎙</div>
        <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--gray-800)', marginBottom: 6 }}>
          面对面采集
        </div>
        <div style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 20, lineHeight: 1.6 }}>
          运营和红人在一起时，直接在此设备上开始 AI 对话采集。
        </div>
        <Input
          placeholder="红人姓名（选填）"
          value={directKolName}
          onChange={e => setDirectKolName(e.target.value)}
          style={{ marginBottom: 12 }}
          onPressEnter={handleDirectStart}
        />
        <button
          className="btn btn-primary"
          style={{ width: '100%' }}
          onClick={handleDirectStart}
          disabled={directLoading}
        >
          {directLoading ? '准备中…' : '开始采集 →'}
        </button>
      </div>

      {/* 卡片 B：远程分享链接 */}
      <div className="card" style={{ padding: '24px 28px' }}>
        <div style={{ fontSize: 28, marginBottom: 12 }}>🔗</div>
        <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--gray-800)', marginBottom: 6 }}>
          远程分享链接
        </div>
        <div style={{ fontSize: 13, color: 'var(--gray-500)', marginBottom: 20, lineHeight: 1.6 }}>
          运营和红人不在一起时，生成链接发给红人，红人自行完成对话采集。
        </div>
        <button
          className="btn btn-ghost"
          style={{ width: '100%' }}
          onClick={() => setShowCreate(true)}
        >
          创建分享链接
        </button>
      </div>

    </div>

    {/* ── 历史链接列表 ── */}
    <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--gray-500)', marginBottom: 12 }}>
      历史链接
    </div>
    <div className="card">
      <div className="card-body" style={{ padding: 0 }}>
        {loading
          ? <div className="empty-state"><div className="empty-state-text">加载中…</div></div>
          : links.length === 0
          ? <div className="empty-state"><div className="empty-state-text">暂无历史链接</div></div>
          : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>红人姓名</th>
                  <th>链接状态</th>
                  <th>到期时间</th>
                  <th>访问时间</th>
                  <th>提交时间</th>
                  <th style={{ textAlign: 'right' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {links.map(lnk => {
                  const expired = isExpired(lnk.expires_at);
                  return (
                    <tr key={lnk.id}>
                      <td>{lnk.kol_name || <span style={{ color: 'var(--gray-400)' }}>未填写</span>}</td>
                      <td>
                        <span className={`badge ${expired ? 'badge-gray' : lnk.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {expired ? '已过期' : lnk.is_active ? '有效' : '停用'}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, color: expired ? 'var(--danger)' : 'var(--gray-700)' }}>
                        {fmtTime(lnk.expires_at)}
                      </td>
                      <td style={{ fontSize: 12 }}>{fmtTime(lnk.used_at)}</td>
                      <td style={{ fontSize: 12 }}>{fmtTime(lnk.submitted_at)}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                          <button className="btn btn-ghost btn-sm"
                            onClick={() => copyLink(lnk.token)}>
                            复制链接
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
      </div>
    </div>

    {/* ── 创建分享链接 Modal（原样保留） ── */}
    <Modal
      title="创建分享链接"
      open={showCreate}
      onCancel={() => { setShowCreate(false); form.resetFields(); }}
      onOk={() => form.submit()}
      okText="创建"
      cancelText="取消"
      destroyOnClose
    >
      <Form form={form} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
        <Form.Item label="红人姓名（可选）" name="kol_name">
          <Input placeholder="预填写，方便识别" />
        </Form.Item>
        <Form.Item label="有效期（小时）" name="expire_hours" initialValue={168}
          rules={[{ required: true }]}>
          <InputNumber min={1} max={720} style={{ width: '100%' }} addonAfter="小时" />
        </Form.Item>
      </Form>
    </Modal>
  </>
);
```

---

## 改动汇总

| # | 改动 |
|---|------|
| 新增 | `useNavigate` import |
| 新增 | `directKolName` / `directLoading` state |
| 新增 | `handleDirectStart()` 函数（创建链接 → navigate） |
| 改动 | `return` 整体替换：双卡片入口 + 历史链接列表 |
| 保留 | `handleCreate` / `copyLink` / `loadLinks` / 创建弹窗，原样不变 |

**改动量**：约 50 行净增，TypeScript 零新 `any`，零新依赖。

---

## 完成后验证

| 验证点 | 预期 |
|--------|------|
| 进入 `/workspace/kol-intake` | 显示两个卡片 + 历史链接表格 |
| 「开始采集」不填姓名直接点 | 自动创建链接，跳转 `/intake/:token`，页面正常加载 |
| 「开始采集」填写姓名后点 | 跳转后对话页面 header 显示「欢迎 XXX」 |
| 「创建分享链接」点击 | 弹出原有创建弹窗 |
| 创建成功后 | 历史链接列表刷新，出现新链接 |
| 历史链接「复制链接」 | 链接复制到剪贴板 |
