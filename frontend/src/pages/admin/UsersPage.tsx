import { useEffect, useState, useCallback, useRef } from 'react';
import { Modal, Form, Input, Select, Popconfirm, message, Typography } from 'antd';
import { pinyin } from 'pinyin-pro';
import {
  getUsers, createUser, updateUser, deleteUser,
  enableUser, disableUser, resetPassword, checkUsername,
} from '../../api/users';
import type { CreateUserRequest, UpdateUserRequest } from '../../api/users';
import type { UserInfo as User } from '../../types/user';
import type { PagedData } from '../../types/api';

const DEFAULT_PASSWORD = 'Mcn@123';

function toPinyinUsername(name: string): string {
  return pinyin(name, { toneType: 'none', separator: '' }).replace(/\s+/g, '').toLowerCase();
}

async function resolveAvailableUsername(base: string): Promise<string> {
  const { available } = await checkUsername(base);
  if (available) return base;
  for (let i = 1; i <= 99; i++) {
    const candidate = `${base}${i}`;
    const { available: ok } = await checkUsername(candidate);
    if (ok) return candidate;
  }
  return `${base}${Date.now()}`;
}

function roleBadge(role: User['role']) {
  const cls = role === 'admin' ? 'badge-brand' : 'badge-gray';
  const label = role === 'admin' ? '管理员' : '运营';
  return <span className={`badge ${cls}`}>{label}</span>;
}

function statusBadge(status: User['status']) {
  const cls = status === 'enabled' ? 'badge-success' : 'badge-gray';
  const label = status === 'enabled' ? '正常' : '停用';
  return <span className={`badge ${cls}`}>{label}</span>;
}

export default function UsersPage() {
  const [data, setData] = useState<PagedData<User> | null>(null);
  const [roleFilter, setRoleFilter] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<User | null>(null);
  const [formLoading, setFormLoading] = useState(false);
  const [resetResult, setResetResult] = useState<{ userName: string; password: string } | null>(null);

  // 标记账号字段是否被手动修改，避免实时覆盖用户输入
  const usernameEditedRef = useRef(false);

  const [createForm] = Form.useForm<CreateUserRequest & { password: string }>();
  const [editForm] = Form.useForm<Pick<UpdateUserRequest, 'real_name' | 'role' | 'new_password'>>();

  // 监听姓名字段，自动生成拼音账号
  const watchedRealName = Form.useWatch('real_name', createForm);
  useEffect(() => {
    if (!watchedRealName || usernameEditedRef.current) return;
    const py = toPinyinUsername(watchedRealName);
    if (py) createForm.setFieldValue('username', py);
  }, [watchedRealName, createForm]);

  const load = useCallback(() => {
    setLoading(true);
    getUsers({ page, page_size: 12, ...(roleFilter ? { role: roleFilter } : {}) })
      .then(setData)
      .catch(() => message.error('加载用户列表失败'))
      .finally(() => setLoading(false));
  }, [page, roleFilter]);

  useEffect(() => { load(); }, [load]);

  function openCreate() {
    usernameEditedRef.current = false;
    createForm.resetFields();
    createForm.setFieldValue('password', DEFAULT_PASSWORD);
    setCreateOpen(true);
  }

  async function handleCreate(values: CreateUserRequest & { password: string }) {
    setFormLoading(true);
    try {
      const baseUsername = values.username.trim();
      const resolvedUsername = await resolveAvailableUsername(baseUsername);
      if (resolvedUsername !== baseUsername) {
        createForm.setFieldValue('username', resolvedUsername);
        message.warning(`账号「${baseUsername}」已被占用，已自动调整为「${resolvedUsername}」`);
        setFormLoading(false);
        return; // 让用户确认后再次提交
      }
      await createUser({ ...values, username: resolvedUsername });
      message.success('账号创建成功');
      setCreateOpen(false);
      createForm.resetFields();
      load();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '创建失败');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleUpdate(values: Pick<UpdateUserRequest, 'real_name' | 'role' | 'new_password'>) {
    if (!editUser) return;
    setFormLoading(true);
    const payload: UpdateUserRequest = { real_name: values.real_name, role: values.role };
    if (values.new_password) payload.new_password = values.new_password;
    try {
      await updateUser(editUser.id, payload);
      message.success('账号信息已更新');
      setEditUser(null);
      load();
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '更新失败');
    } finally {
      setFormLoading(false);
    }
  }

  async function handleResetPassword(user: User) {
    try {
      const res = await resetPassword(user.id);
      setResetResult({ userName: user.real_name, password: res.initial_password });
    } catch {
      message.error('重置失败');
    }
  }

  async function handleToggle(user: User) {
    try {
      if (user.status === 'enabled') {
        await disableUser(user.id);
        message.success('账号已停用');
      } else {
        await enableUser(user.id);
        message.success('账号已启用');
      }
      load();
    } catch {
      message.error('操作失败');
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteUser(id);
      message.success('账号已删除');
      load();
    } catch {
      message.error('删除失败');
    }
  }

  const total = data?.pagination.total ?? 0;
  const totalPages = data?.pagination.total_pages ?? Math.ceil(total / 12);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">用户管理</h1>
          <p className="page-desc">管理平台运营账号与权限</p>
        </div>
        <div className="page-actions">
          <button className="btn btn-primary" onClick={openCreate}>+ 新增账号</button>
        </div>
      </div>

      <div className="card">
        <div className="filter-bar">
          <select
            className="filter-select"
            value={roleFilter}
            onChange={e => { setRoleFilter(e.target.value); setPage(1); }}
          >
            <option value="">全部角色</option>
            <option value="admin">管理员</option>
            <option value="operator">运营</option>
          </select>
          <span className="filter-count">共 {total} 名用户</span>
        </div>

        {loading ? (
          <div className="empty-state"><div className="empty-state-text">加载中...</div></div>
        ) : !data || data.items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-text">暂无用户</div>
          </div>
        ) : (
          <>
          <table className="ant-table">
            <thead>
              <tr>
                <th style={{ width: 52 }}>序号</th>
                <th>姓名</th>
                <th>账号</th>
                <th>密码</th>
                <th>角色</th>
                <th>状态</th>
                <th>最近登录</th>
                <th className="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((u, idx) => (
                <tr key={u.id}>
                  <td style={{ color: 'var(--gray-400)', fontSize: 12, textAlign: 'center' }}>
                    {(page - 1) * 12 + idx + 1}
                  </td>
                  <td style={{ fontWeight: 600, color: 'var(--gray-800)' }}>{u.real_name}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--gray-600)' }}>{u.username}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--gray-300)', letterSpacing: 2 }}>••••••••</td>
                  <td>{roleBadge(u.role)}</td>
                  <td>{statusBadge(u.status)}</td>
                  <td style={{ color: 'var(--gray-400)', fontSize: 12 }}>
                    {u.last_login_at
                      ? new Date(u.last_login_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                      : '从未登录'}
                  </td>
                  <td className="col-actions">
                    {/* 编辑 */}
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        setEditUser(u);
                        editForm.setFieldsValue({ real_name: u.real_name, role: u.role, new_password: undefined });
                      }}
                    >
                      编辑
                    </button>

                    {/* 重置密码 */}
                    <Popconfirm
                      title={`确认将 ${u.real_name} 的密码重置为初始密码？`}
                      description={<span>重置后密码为 <strong style={{ fontFamily: 'monospace', color: 'var(--accent)' }}>{DEFAULT_PASSWORD}</strong></span>}
                      okText="确认重置"
                      cancelText="取消"
                      onConfirm={() => handleResetPassword(u)}
                    >
                      <button className="btn btn-ghost btn-sm">重置密码</button>
                    </Popconfirm>

                    {/* 停用 / 启用 */}
                    {u.status === 'enabled' ? (
                      <Popconfirm
                        title={`确认停用用户「${u.real_name}」？`}
                        description="停用后该账号将无法登录。"
                        okText="确认停用"
                        cancelText="取消"
                        okButtonProps={{ danger: true }}
                        onConfirm={() => handleToggle(u)}
                      >
                        <button className="btn btn-ghost btn-sm">停用</button>
                      </Popconfirm>
                    ) : (
                      <Popconfirm
                        title={`确认启用账号「${u.real_name}」？`}
                        description="启用后该账号可正常登录。"
                        okText="确认启用"
                        cancelText="取消"
                        onConfirm={() => handleToggle(u)}
                      >
                        <button className="btn btn-ghost btn-sm">启用</button>
                      </Popconfirm>
                    )}

                    {/* 删除 */}
                    <Popconfirm
                      title={`确认删除用户「${u.real_name}」？`}
                      description="此操作不可恢复。"
                      okText="确认删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => handleDelete(u.id)}
                    >
                      <button className="btn btn-danger-ghost btn-sm">删除</button>
                    </Popconfirm>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {total > 12 && (
            <div className="pagination">
              <span>共 {total} 名用户</span>
              <div className="pages">
                <div className="page-btn" onClick={() => setPage(p => Math.max(1, p - 1))}>‹</div>
                {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => i + 1).map(p => (
                  <div key={p} className={`page-btn${page === p ? ' active' : ''}`} onClick={() => setPage(p)}>{p}</div>
                ))}
                <div className="page-btn" onClick={() => setPage(p => Math.min(totalPages, p + 1))}>›</div>
              </div>
            </div>
          )}
          </>
        )}
      </div>

      {/* 新增账号弹窗 */}
      <Modal
        title="新增账号"
        open={createOpen}
        onCancel={() => { setCreateOpen(false); createForm.resetFields(); }}
        onOk={() => createForm.submit()}
        okText="创建"
        cancelText="取消"
        confirmLoading={formLoading}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Form.Item
            label="姓名"
            name="real_name"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>
          <Form.Item
            label="账号"
            name="username"
            rules={[{ required: true, message: '请输入账号' }]}
          >
            <Input
              placeholder="自动生成，可手动修改"
              onChange={() => { usernameEditedRef.current = true; }}
            />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="请输入初始密码" />
          </Form.Item>
          <Form.Item
            label="角色"
            name="role"
            rules={[{ required: true, message: '请选择角色' }]}
            initialValue="operator"
          >
            <Select>
              <Select.Option value="admin">管理员</Select.Option>
              <Select.Option value="operator">运营</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑账号弹窗 */}
      <Modal
        title={`编辑账号：${editUser?.real_name ?? ''}`}
        open={!!editUser}
        onCancel={() => { setEditUser(null); editForm.resetFields(); }}
        onOk={() => editForm.submit()}
        okText="保存"
        cancelText="取消"
        confirmLoading={formLoading}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate} style={{ marginTop: 16 }}>
          <Form.Item
            label="姓名"
            name="real_name"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="请输入姓名" />
          </Form.Item>
          <Form.Item label="账号">
            <Input value={editUser?.username ?? ''} disabled />
          </Form.Item>
          <Form.Item
            label="密码"
            name="new_password"
          >
            <Input.Password placeholder="留空则不修改密码" />
          </Form.Item>
          <Form.Item
            label="角色"
            name="role"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Select>
              <Select.Option value="admin">管理员</Select.Option>
              <Select.Option value="operator">运营</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
      {/* 重置密码结果弹窗 */}
      <Modal
        title="密码重置成功"
        open={!!resetResult}
        onOk={() => setResetResult(null)}
        onCancel={() => setResetResult(null)}
        okText="我知道了"
        cancelButtonProps={{ style: { display: 'none' } }}
        centered
      >
        <div style={{ textAlign: 'center', padding: '24px 0 8px' }}>
          <p style={{ color: 'var(--gray-600)', marginBottom: 16 }}>
            <strong>{resetResult?.userName}</strong> 的密码已重置，新密码为：
          </p>
          <Typography.Text
            copyable={{ tooltips: ['点击复制', '已复制'] }}
            style={{
              fontSize: 22,
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              color: 'var(--accent)',
              letterSpacing: 2,
            }}
          >
            {resetResult?.password}
          </Typography.Text>
          <p style={{ color: 'var(--gray-400)', fontSize: 12, marginTop: 16 }}>
            请将新密码告知用户，该提示关闭后不再显示
          </p>
        </div>
      </Modal>
    </>
  );
}
