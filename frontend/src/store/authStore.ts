import { create } from 'zustand';
import type { UserInfo } from '../types/user';

const TOKEN_KEY = 'mcn_token';

interface AuthState {
  token: string | null;
  user: UserInfo | null;
  isAuthenticated: boolean;
  mustChangePassword: boolean;
  setAuth: (token: string, user: UserInfo, mustChangePassword: boolean) => void;
  clearAuth: () => void;
  updateUser: (user: UserInfo) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem(TOKEN_KEY),
  user: null,
  isAuthenticated: !!localStorage.getItem(TOKEN_KEY),
  mustChangePassword: false,

  setAuth: (token, user, mustChangePassword) => {
    localStorage.setItem(TOKEN_KEY, token);
    set({ token, user, isAuthenticated: true, mustChangePassword });
  },

  clearAuth: () => {
    localStorage.removeItem(TOKEN_KEY);
    set({ token: null, user: null, isAuthenticated: false, mustChangePassword: false });
  },

  updateUser: (user) => {
    set({ user, mustChangePassword: user.must_change_password });
  },
}));
