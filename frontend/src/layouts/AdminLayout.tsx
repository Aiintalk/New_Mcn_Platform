import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { logout } from '../api/auth';
import { message } from 'antd';

type NavLink  = { path: string; label: string };
type NavGroup = { title: string; items: NavLink[] };

const GROUPS: NavGroup[] = [
  {
    title: '功能管理',
    items: [
      { path: '/admin',           label: '仪表盘' },
      { path: '/admin/users',     label: '用户管理' },
      { path: '/admin/kols',      label: '红人管理' },
      { path: '/admin/workspace', label: '工具配置' },
      { path: '/admin/tasks',     label: '任务记录' },
      { path: '/admin/outputs',   label: '产出记录' },
    ],
  },
  {
    title: '系统管理',
    items: [
      { path: '/admin/system',  label: '服务状态' },
      { path: '/admin/config',  label: '服务配置' },
      { path: '/admin/audit',   label: '操作日志' },
      { path: '/admin/logs',    label: '调用日志' },
    ],
  },
];

function findLabel(pathname: string): string {
  for (const group of GROUPS) {
    const found = group.items.find(n => n.path === pathname);
    if (found) return found.label;
  }
  return '页面';
}

export default function AdminLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user, clearAuth } = useAuthStore();
  const displayName = user?.real_name || user?.username || 'A';
  const currentLabel = findLabel(pathname);

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
          <p>AI 内容运营平台 · 管理后台</p>
        </div>
        <nav className="sidebar-nav">
          {GROUPS.map(g => (
            <div key={g.title} className="nav-group">
              <div className="nav-group-title">{g.title}</div>
              {g.items.map(n => (
                <div
                  key={n.path}
                  className={pathname === n.path ? 'nav-item active' : 'nav-item'}
                  onClick={() => navigate(n.path)}
                >
                  <span>{n.label}</span>
                </div>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">{displayName.charAt(0)}</div>
            <div>
              <div className="user-name">{displayName}</div>
              <div className="user-role">管理员</div>
            </div>
          </div>
          <button className="btn-logout" onClick={handleLogout}>退出登录</button>
        </div>
      </aside>

      <div className="main-content">
        <div className="topbar">
          <div className="breadcrumb">管理后台 / <span>{currentLabel}</span></div>
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
