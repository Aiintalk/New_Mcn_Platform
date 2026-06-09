import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AuthLayout from './layouts/AuthLayout';
import OperatorLayout from './layouts/OperatorLayout';
import AdminLayout from './layouts/AdminLayout';
import ProtectedRoute from './routes/ProtectedRoute';
import AdminRoute from './routes/AdminRoute';
import LoginPage from './pages/auth/LoginPage';
import ChangePasswordPage from './pages/auth/ChangePasswordPage';
import HomePage from './pages/operator/HomePage';
import WorkspacePage from './pages/operator/WorkspacePage';
import PersonaWriterPage from './pages/operator/PersonaWriterPage';
import OperatorIntakePage from './pages/operator/OperatorIntakePage';
import OperatorIntakeChatPage from './pages/operator/OperatorIntakeChatPage';
import TasksPage from './pages/operator/TasksPage';
import OutputsPage from './pages/operator/OutputsPage';
import AdminDashboardPage from './pages/admin/AdminDashboardPage';
import UsersPage from './pages/admin/UsersPage';
import KolsPage from './pages/admin/KolsPage';
import WorkspaceConfigPage from './pages/admin/WorkspaceConfigPage';
import AdminTasksPage from './pages/admin/AdminTasksPage';
import AdminOutputsPage from './pages/admin/AdminOutputsPage';
import ServiceStatusPage from './pages/admin/ServiceStatusPage';
import ServiceConfigPage from './pages/admin/ServiceConfigPage';
import ExternalLogsPage from './pages/admin/ExternalLogsPage';
import OperationLogsPage from './pages/admin/OperationLogsPage';
import AdminIntakePage from './pages/admin/AdminIntakePage';
import IntakePage from './pages/intake/IntakePage';

function Page403() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: 64, fontWeight: 700, color: 'var(--gray-200)' }}>403</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--gray-700)' }}>无权限访问</div>
      <div style={{ fontSize: 14, color: 'var(--gray-400)' }}>您没有访问此页面的权限，请联系管理员</div>
    </div>
  );
}

function Page404() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', flexDirection: 'column', gap: 16 }}>
      <div style={{ fontSize: 64, fontWeight: 700, color: 'var(--gray-200)' }}>404</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--gray-700)' }}>页面不存在</div>
      <div style={{ fontSize: 14, color: 'var(--gray-400)' }}>您访问的页面不存在或已被移除</div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
        </Route>

        {/* Public intake page — no auth needed */}
        <Route path="/intake/:token" element={<IntakePage />} />

        {/* Change password — protected but no shell */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AuthLayout />}>
            <Route path="/change-password" element={<ChangePasswordPage />} />
          </Route>
        </Route>

        {/* Operator routes */}
        <Route element={<ProtectedRoute />}>
          <Route element={<OperatorLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/workspace/persona-writer" element={<PersonaWriterPage />} />
            <Route path="/workspace/kol-intake" element={<OperatorIntakePage />} />
            <Route path="/workspace/kol-intake/chat" element={<OperatorIntakeChatPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/outputs" element={<OutputsPage />} />
          </Route>
        </Route>

        {/* Admin routes */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AdminRoute />}>
            <Route element={<AdminLayout />}>
              <Route path="/admin" element={<AdminDashboardPage />} />
              <Route path="/admin/users" element={<UsersPage />} />
              <Route path="/admin/kols" element={<KolsPage />} />
              <Route path="/admin/workspace" element={<WorkspaceConfigPage />} />
              <Route path="/admin/tasks" element={<AdminTasksPage />} />
              <Route path="/admin/outputs" element={<AdminOutputsPage />} />
              <Route path="/admin/system" element={<ServiceStatusPage />} />
              <Route path="/admin/logs" element={<ExternalLogsPage />} />
              <Route path="/admin/audit" element={<OperationLogsPage />} />
              <Route path="/admin/config" element={<ServiceConfigPage />} />
              <Route path="/admin/intake" element={<AdminIntakePage />} />
            </Route>
          </Route>
        </Route>

        {/* Error pages */}
        <Route path="/403" element={<Page403 />} />
        <Route path="/404" element={<Page404 />} />
        <Route path="*" element={<Navigate to="/404" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
