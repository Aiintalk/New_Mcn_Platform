import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '../../../store/authStore';
import type { UserInfo } from '../../../types/user';

function makeUser(overrides: Partial<UserInfo> = {}): UserInfo {
  return {
    id: 1,
    username: 'admin',
    real_name: 'Admin',
    role: 'admin',
    status: 'enabled',
    must_change_password: false,
    last_login_at: null,
    ...overrides,
  };
}

describe('authStore', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      token: null,
      user: null,
      isAuthenticated: false,
      mustChangePassword: false,
    });
  });

  it('initial state has no token and is not authenticated', () => {
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.mustChangePassword).toBe(false);
  });

  it('setAuth stores token in localStorage and updates state', () => {
    const user = makeUser();

    useAuthStore.getState().setAuth('test-token-123', user, false);

    const state = useAuthStore.getState();
    expect(state.token).toBe('test-token-123');
    expect(state.user).toEqual(user);
    expect(state.isAuthenticated).toBe(true);
    expect(state.mustChangePassword).toBe(false);
    expect(localStorage.getItem('mcn_token')).toBe('test-token-123');
  });

  it('setAuth with mustChangePassword=true sets flag', () => {
    const user = makeUser({ id: 2, username: 'newuser', must_change_password: true });

    useAuthStore.getState().setAuth('token-456', user, true);

    expect(useAuthStore.getState().mustChangePassword).toBe(true);
  });

  it('clearAuth removes token from localStorage and resets state', () => {
    const user = makeUser();

    useAuthStore.getState().setAuth('token', user, false);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    useAuthStore.getState().clearAuth();

    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.mustChangePassword).toBe(false);
    expect(localStorage.getItem('mcn_token')).toBeNull();
  });

  it('updateUser updates user and mustChangePassword flag', () => {
    const user = makeUser();

    useAuthStore.getState().setAuth('token', user, false);

    const updatedUser = { ...user, real_name: 'Updated', must_change_password: true };
    useAuthStore.getState().updateUser(updatedUser);

    const state = useAuthStore.getState();
    expect(state.user?.real_name).toBe('Updated');
    expect(state.mustChangePassword).toBe(true);
  });

  it('isAuthenticated is true when token is set', () => {
    const user = makeUser();
    useAuthStore.getState().setAuth('existing-token', user, false);

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().token).toBe('existing-token');
  });
});
