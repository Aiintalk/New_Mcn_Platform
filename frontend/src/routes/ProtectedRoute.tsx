import { useEffect, useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { getMe } from '../api/auth';

export default function ProtectedRoute() {
  const { token, mustChangePassword, clearAuth, updateUser } = useAuthStore();
  const location = useLocation();
  const [checking, setChecking] = useState(true);
  const [valid, setValid] = useState(false);

  useEffect(() => {
    if (!token) {
      setChecking(false);
      return;
    }
    getMe()
      .then((user) => {
        updateUser(user);
        setValid(true);
      })
      .catch(() => {
        clearAuth();
        setValid(false);
      })
      .finally(() => setChecking(false));
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (checking) {
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>加载中...</div>;
  }

  if (!valid) {
    return <Navigate to="/login" replace />;
  }

  if (mustChangePassword && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  return <Outlet />;
}
