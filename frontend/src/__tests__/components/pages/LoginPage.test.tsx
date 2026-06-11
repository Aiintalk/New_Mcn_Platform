import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LoginPage from '../../../pages/auth/LoginPage';

// Mock auth API
const mockLogin = vi.fn();
vi.mock('../../../api/auth', () => ({
  login: (...args: unknown[]) => mockLogin(...args),
}));

// Mock authStore
const mockSetAuth = vi.fn();
vi.mock('../../../store/authStore', () => ({
  useAuthStore: () => ({
    setAuth: mockSetAuth,
  }),
}));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/admin" element={<div>Admin Page</div>} />
        <Route path="/change-password" element={<div>Change Password Page</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders username and password inputs and login button', () => {
    renderLogin();
    expect(screen.getByPlaceholderText(/请输入账号/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/请输入密码/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /登录/ })).toBeInTheDocument();
  });

  it('displays the app title and subtitle', () => {
    renderLogin();
    expect(screen.getByText(/达人说 AI 内容运营平台/)).toBeInTheDocument();
    expect(screen.getByText(/请使用您的账号登录/)).toBeInTheDocument();
  });

  it('toggles admin mode on button click', async () => {
    const user = userEvent.setup();
    renderLogin();

    expect(screen.getByText(/管理员登录/)).toBeInTheDocument();

    await user.click(screen.getByText(/管理员登录/));
    expect(screen.getByText(/管理员登录$/)).toBeInTheDocument();
    expect(screen.getByText(/返回运营登录/)).toBeInTheDocument();
  });

  it('displays footer text', () => {
    renderLogin();
    expect(screen.getByText(/内部系统/)).toBeInTheDocument();
    expect(screen.getByText(/忘记密码请联系管理员/)).toBeInTheDocument();
  });

  it('renders login button as submit button', () => {
    renderLogin();
    const submitButtons = screen.getAllByRole('button');
    const loginBtn = submitButtons.find(b => b.getAttribute('type') === 'submit');
    expect(loginBtn).toBeTruthy();
  });
});
