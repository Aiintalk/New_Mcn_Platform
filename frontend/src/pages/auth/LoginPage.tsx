import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button } from 'antd';
import { login } from '../../api/auth';
import { useAuthStore } from '../../store/authStore';

interface LoginFormValues {
  username: string;
  password: string;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [adminMode, setAdminMode] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSubmit(values: LoginFormValues) {
    setErrorMsg(null);
    setLoading(true);
    try {
      const res = await login(values.username, values.password);
      setAuth(res.access_token, res.user, res.must_change_password);
      if (res.must_change_password) {
        navigate('/change-password', { replace: true });
      } else if (adminMode) {
        navigate('/admin', { replace: true });
      } else {
        navigate('/', { replace: true });
      }
    } catch (err: unknown) {
      const code = (err as { code?: string }).code;
      if (code === 'AUTH_INVALID_PASSWORD' || code === 'AUTH_USER_NOT_FOUND') {
        setErrorMsg('账号或密码错误，请重新输入');
      } else if (code === 'AUTH_USER_DISABLED') {
        setErrorMsg('账号已停用，请联系管理员');
      } else {
        setErrorMsg(err instanceof Error ? err.message : '登录失败，请重试');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-card">
      <div className="login-logo">达</div>
      <h1 className="auth-title" style={{ textAlign: 'center', marginBottom: 4 }}>达人说 AI 内容运营平台</h1>
      <p className="login-subtitle">
        {adminMode ? '管理员登录' : '请使用您的账号登录'}
      </p>

      <Form layout="vertical" onFinish={handleSubmit} autoComplete="off">
        <Form.Item
          label="账号"
          name="username"
          rules={[{ required: true, message: '请输入账号' }]}
        >
          <Input
            placeholder="请输入账号"
            size="large"
            onChange={() => setErrorMsg(null)}
          />
        </Form.Item>
        <Form.Item
          label="密码"
          name="password"
          rules={[{ required: true, message: '请输入密码' }]}
          style={{ marginBottom: errorMsg ? 8 : 24 }}
        >
          <Input.Password
            placeholder="请输入密码"
            size="large"
            onChange={() => setErrorMsg(null)}
          />
        </Form.Item>

        {errorMsg && (
          <div style={{
            marginBottom: 16,
            padding: '8px 12px',
            background: '#fff2f0',
            border: '1px solid #ffccc7',
            borderRadius: 8,
            color: '#cf1322',
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            <span>⚠</span>
            <span>{errorMsg}</span>
          </div>
        )}

        <Form.Item style={{ marginBottom: 0 }}>
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            style={{ background: 'var(--accent)', borderColor: 'var(--accent)' }}
          >
            登录
          </Button>
        </Form.Item>
      </Form>

      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <button
          className="login-mode-toggle"
          onClick={() => setAdminMode(v => !v)}
        >
          {adminMode ? '← 返回运营登录' : '管理员登录'}
        </button>
      </div>

      <p className="login-footer">内部系统 · 忘记密码请联系管理员</p>
    </div>
  );
}
