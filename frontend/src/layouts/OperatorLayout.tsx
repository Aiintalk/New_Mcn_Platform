import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { logout } from '../api/auth';
import { message } from 'antd';

const MENU = [
  { path: '/',          label: '概览',     icon: '⊞' },
  { path: '/workspace', label: '创作中心', icon: '✦' },
  { path: '/tasks',     label: '任务中心', icon: '☑' },
  { path: '/outputs',   label: '产出中心', icon: '⬇' },
];

export default function OperatorLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, clearAuth } = useAuthStore();
  const displayName = user?.real_name || user?.username || 'U';
  const currentLabel = MENU.find(n => n.path === pathname)?.label
    ?? MENU.slice().reverse().find(n => pathname.startsWith(n.path))?.label
    ?? '页面';

  async function handleLogout() {
    try { await logout(); } catch { /* ignore */ }
    clearAuth();
    navigate('/login');
    message.success('已退出登录');
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>达人说</h1>
          <p>AI 内容运营平台</p>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-group">
            {MENU.map(n => (
              <div
                key={n.path}
                className={pathname === n.path ? 'nav-item active' : 'nav-item'}
                onClick={() => navigate(n.path)}
              >
                <span className="nav-icon">{n.icon}</span>
                <span>{n.label}</span>
              </div>
            ))}
          </div>
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{displayName.charAt(0)}</div>
            <div>
              <div className="user-name">{displayName}</div>
              <div className="user-role">运营</div>
            </div>
          </div>
          <button className="btn-logout" onClick={handleLogout}>退出登录</button>
        </div>
      </aside>

      <div className="main-content">
        <div className="topbar">
          <div className="breadcrumb">达人说 / <span>{currentLabel}</span></div>
          <div className="topbar-right">
            <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>{user?.real_name}</span>
          </div>
        </div>
        <div className="main-body">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
