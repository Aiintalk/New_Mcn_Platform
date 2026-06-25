import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AuthLayout from './layouts/AuthLayout';
import OperatorLayout from './layouts/OperatorLayout';
import AdminLayout from './layouts/AdminLayout';
import ProtectedRoute from './routes/ProtectedRoute';
import AdminRoute from './routes/AdminRoute';

// 页面组件懒加载：每个页面拆成独立 chunk，按需加载
const LoginPage = lazy(() => import('./pages/auth/LoginPage'));
const ChangePasswordPage = lazy(() => import('./pages/auth/ChangePasswordPage'));
const HomePage = lazy(() => import('./pages/operator/HomePage'));
const WorkspacePage = lazy(() => import('./pages/operator/WorkspacePage'));
const PersonaWriterPage = lazy(() => import('./pages/operator/PersonaWriterPage'));
const SeedingWriterPage = lazy(() => import('./pages/operator/SeedingWriterPage'));
const PersonaPage = lazy(() => import('./pages/operator/PersonaPage'));
const PersonaReviewPage = lazy(() => import('./pages/operator/PersonaReviewPage'));
const OperatorIntakePage = lazy(() => import('./pages/operator/OperatorIntakePage'));
const OperatorIntakeChatPage = lazy(() => import('./pages/operator/OperatorIntakeChatPage'));
const TasksPage = lazy(() => import('./pages/operator/TasksPage'));
const OutputsPage = lazy(() => import('./pages/operator/OutputsPage'));
const AdminDashboardPage = lazy(() => import('./pages/admin/AdminDashboardPage'));
const UsersPage = lazy(() => import('./pages/admin/UsersPage'));
const KolsPage = lazy(() => import('./pages/admin/KolsPage'));
const WorkspaceConfigPage = lazy(() => import('./pages/admin/WorkspaceConfigPage'));
const AdminTasksPage = lazy(() => import('./pages/admin/AdminTasksPage'));
const AdminOutputsPage = lazy(() => import('./pages/admin/AdminOutputsPage'));
const ServiceStatusPage = lazy(() => import('./pages/admin/ServiceStatusPage'));
const ServiceConfigPage = lazy(() => import('./pages/admin/ServiceConfigPage'));
const ExternalLogsPage = lazy(() => import('./pages/admin/ExternalLogsPage'));
const OperationLogsPage = lazy(() => import('./pages/admin/OperationLogsPage'));
const AdminIntakePage = lazy(() => import('./pages/admin/AdminIntakePage'));
const IntakePage = lazy(() => import('./pages/intake/IntakePage'));
const BenchmarkPage = lazy(() => import('./pages/operator/BenchmarkPage'));
const TiktokWriterPage = lazy(() => import('./pages/operator/TiktokWriterPage'));
const SellingPointPage = lazy(() => import('./pages/operator/SellingPointPage'));
const QianchuanReviewPage = lazy(() => import('./pages/operator/QianchuanReviewPage'));
const QianChuanEditReviewPage = lazy(() => import('./pages/operator/QianChuanEditReviewPage'));
const QianchuanPreviewPage = lazy(() => import('./pages/operator/QianchuanPreviewPage'));
const QianchuanCollectionPage = lazy(() => import('./pages/operator/QianchuanCollectionPage'));
const TiktokReviewPage = lazy(() => import('./pages/operator/TiktokReviewPage'));
const LivestreamWriterPage = lazy(() => import('./pages/operator/LivestreamWriterPage'));
const LivestreamReviewPage = lazy(() => import('./pages/operator/LivestreamReviewPage'));
const QianchuanWriterPage = lazy(() => import('./pages/operator/QianchuanWriterPage'));
const MaterialLibraryPage = lazy(() => import('./pages/operator/MaterialLibraryPage'));

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

// Lazy 页面加载时的占位（轻量内联，不引入额外组件避免污染主 bundle）
function PageFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--gray-400)' }}>
      加载中…
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageFallback />}>
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
              <Route path="/workspace/seeding-writer" element={<SeedingWriterPage />} />
              <Route path="/workspace/persona-positioning" element={<PersonaPage />} />
              <Route path="/workspace/benchmark" element={<BenchmarkPage />} />
              <Route path="/workspace/tiktok-writer" element={<TiktokWriterPage />} />
              <Route path="/workspace/tiktok-review" element={<TiktokReviewPage />} />
              <Route path="/workspace/selling-point-extractor" element={<SellingPointPage />} />
              <Route path="/workspace/qianchuan-review" element={<QianchuanReviewPage />} />
              <Route path="/workspace/qianchuan-edit-review" element={<QianChuanEditReviewPage />} />
              <Route path="/workspace/qianchuan-preview" element={<QianchuanPreviewPage />} />
              <Route path="/workspace/qianchuan-collection" element={<QianchuanCollectionPage />} />
              <Route path="/workspace/livestream-writer" element={<LivestreamWriterPage />} />
              <Route path="/workspace/livestream-review" element={<LivestreamReviewPage />} />
              <Route path="/workspace/qianchuan-writer" element={<QianchuanWriterPage />} />
              <Route path="/workspace/material-library" element={<MaterialLibraryPage />} />
              <Route path="/workspace/persona-review" element={<PersonaReviewPage />} />
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
      </Suspense>
    </BrowserRouter>
  );
}
