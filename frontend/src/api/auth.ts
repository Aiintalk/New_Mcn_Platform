import { get, post } from './request';
import type { LoginResponse, UserInfo } from '../types/user';

export async function login(username: string, password: string): Promise<LoginResponse> {
  return post<LoginResponse>('/api/auth/login', { username, password });
}

export async function getMe(): Promise<UserInfo> {
  return get<UserInfo>('/api/auth/me');
}

export async function changePassword(
  old_password: string,
  new_password: string,
  confirm_password: string
): Promise<void> {
  await post<null>('/api/auth/change-password', {
    old_password,
    new_password,
    confirm_password,
  });
}

export async function logout(): Promise<void> {
  await post<null>('/api/auth/logout');
}
