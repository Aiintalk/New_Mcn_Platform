import { get, post, patch, del } from './request';
import type { UserInfo } from '../types/user';
import type { PagedData } from '../types/api';

export interface UserListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  status?: string;
  role?: string;
}

export interface CreateUserRequest {
  username: string;
  real_name: string;
  role: 'admin' | 'operator';
  password?: string;
}

export interface CreateUserResponse {
  id: number;
  username: string;
  real_name: string;
  role: 'admin' | 'operator';
  status: string;
  initial_password: string;
}

export interface UpdateUserRequest {
  real_name?: string;
  role?: 'admin' | 'operator';
  status?: string;
  new_password?: string;
}

export interface ResetPasswordResponse {
  initial_password: string;
}

export async function checkUsername(username: string): Promise<{ available: boolean }> {
  return get<{ available: boolean }>('/api/admin/users/check-username', { username });
}

export async function getUsers(params?: UserListParams): Promise<PagedData<UserInfo>> {
  return get<PagedData<UserInfo>>('/api/admin/users', params as Record<string, string | number | boolean | undefined>);
}

export async function createUser(data: CreateUserRequest): Promise<CreateUserResponse> {
  return post<CreateUserResponse>('/api/admin/users', data);
}

export async function updateUser(id: number, data: UpdateUserRequest): Promise<UserInfo> {
  return patch<UserInfo>(`/api/admin/users/${id}`, data);
}

export async function resetPassword(id: number): Promise<ResetPasswordResponse> {
  return post<ResetPasswordResponse>(`/api/admin/users/${id}/reset-password`);
}

export async function enableUser(id: number): Promise<void> {
  await post<null>(`/api/admin/users/${id}/enable`);
}

export async function disableUser(id: number): Promise<void> {
  await post<null>(`/api/admin/users/${id}/disable`);
}

export async function deleteUser(id: number): Promise<void> {
  await del<null>(`/api/admin/users/${id}`);
}
