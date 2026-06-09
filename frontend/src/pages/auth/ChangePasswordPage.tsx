import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, message } from 'antd';
import { changePassword } from '../../api/auth';
import { useAuthStore } from '../../store/authStore';

interface FormValues {
  old_password: string;
  new_password: string;
  confirm_password: string;
}

export default function ChangePasswordPage() {
  const navigate = useNavigate();
  const { clearAuth } = useAuthStore();
  const [loading, setLoading] = useState(false);

  async function handleSubmit(values: FormValues) {
    if (values.new_password !== values.confirm_password) {
      message.error('两次输入的新密码不一致');
      return;
    }
    setLoading(true);
    try {
      await changePassword(values.old_password, values.new_password, values.confirm_password);
      clearAuth();
      message.success('密码已修改，请重新登录');
      navigate('/login', { replace: true });
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '密码修改失败，请重试');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-card">
      <div className="auth-logo">
        <div className="auth-logo-icon">达</div>
      </div>
      <h1 className="auth-title" style={{ textAlign: 'center', marginBottom: 4 }}>修改密码</h1>
      <p className="auth-subtitle">首次登录请修改初始密码</p>

      <Form layout="vertical" onFinish={handleSubmit} autoComplete="off">
        <Form.Item
          label="当前密码"
          name="old_password"
          rules={[{ required: true, message: '请输入当前密码' }]}
        >
          <Input.Password size="large" />
        </Form.Item>
        <Form.Item
          label="新密码"
          name="new_password"
          rules={[
            { required: true, message: '请输入新密码' },
            { min: 8, message: '密码至少 8 位' },
          ]}
        >
          <Input.Password size="large" />
        </Form.Item>
        <Form.Item
          label="确认新密码"
          name="confirm_password"
          rules={[{ required: true, message: '请确认新密码' }]}
        >
          <Input.Password size="large" />
        </Form.Item>
        <Form.Item style={{ marginTop: 24, marginBottom: 0 }}>
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={loading}
            style={{ background: 'var(--accent)', borderColor: 'var(--accent)' }}
          >
            确认修改
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}
