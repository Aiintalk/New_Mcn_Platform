import { get, post, patch, del } from './request';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface OssStatsOverview {
  total_calls: number;
  today_calls: number;
  avg_latency_ms: number | null;
  active_keys: number;
  total_keys: number;
}

export interface OssOperationStat {
  operation: string; // upload / download / delete
  calls: number;
  percentage: number; // 0-100
}

export interface OssTrendItem {
  date: string; // "06-04"
  calls: number;
}

export interface OssUserRank {
  user_id: number;
  username: string;
  calls: number;
}

export interface OssStatsResponse {
  overview: OssStatsOverview;
  operations: OssOperationStat[];
  users: OssUserRank[];
  trend: OssTrendItem[];
}

export interface OssOperationDetail {
  operation: string;
  calls: number;
  percentage: number; // 0-100
  avg_latency_ms: number | null;
  success_rate: number | null; // 0-1
}

export interface OssUserDetail {
  user_id: number;
  username: string;
  role: string;
  calls: number;
  last_called_at: string | null;
}

export interface OssCredential {
  id: number;
  provider: string;
  label: string;
  secret_tail: string;
  status: string; // 'enabled' | 'disabled'
  weight: number;
  quota_limit: number | null;
  quota_used: number;
  fail_count: number;
  cooldown_until: string | null;
  config: {
    access_key_id?: string;
    bucket?: string;
    endpoint?: string;
  } | null;
  last_tested_at: string | null;
  last_latency_ms: number | null;
  created_at: string;
}

export interface CreateOssCredentialRequest {
  provider: string;
  label: string;
  api_key: string;
  weight?: number;
  quota_limit?: number | null;
  config?: {
    access_key_id: string;
    bucket: string;
    endpoint: string;
  } | null;
}

export interface UpdateOssCredentialRequest {
  label?: string;
  status?: string;
  weight?: number;
  quota_limit?: number | null;
  config?: {
    access_key_id: string;
    bucket: string;
    endpoint: string;
  } | null;
  api_key?: string;
}

export interface OssTestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  bucket?: string;
  location?: string;
  creation_date?: string;
  error?: string;
}

// ── API functions ──────────────────────────────────────────────────────────────

export async function getOssStats(): Promise<OssStatsResponse> {
  return get<OssStatsResponse>('/api/admin/oss/stats');
}

export async function getOssOperations(): Promise<OssOperationDetail[]> {
  const res = await get<unknown>('/api/admin/oss/operations');
  return Array.isArray(res) ? (res as OssOperationDetail[]) : [];
}

export async function getOssUsers(params?: {
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<{ items: OssUserDetail[]; total: number }> {
  return get<{ items: OssUserDetail[]; total: number }>('/api/admin/oss/users', params);
}

export async function getOssCredentials(params?: {
  provider?: string;
  page?: number;
  page_size?: number;
}): Promise<{ items: OssCredential[]; pagination: { page: number; page_size: number; total: number; total_pages: number } }> {
  return get<{ items: OssCredential[]; pagination: { page: number; page_size: number; total: number; total_pages: number } }>(
    '/api/admin/config/credentials',
    params
  );
}

export async function createOssCredential(data: CreateOssCredentialRequest): Promise<OssCredential> {
  return post<OssCredential>('/api/admin/config/credentials', data);
}

export async function updateOssCredential(id: number, data: UpdateOssCredentialRequest): Promise<OssCredential> {
  return patch<OssCredential>(`/api/admin/config/credentials/${id}`, data);
}

export async function deleteOssCredential(id: number): Promise<void> {
  return del<void>(`/api/admin/config/credentials/${id}`);
}

export async function enableOssCredential(id: number): Promise<OssCredential> {
  return post<OssCredential>(`/api/admin/config/credentials/${id}/enable`, {});
}

export async function disableOssCredential(id: number): Promise<OssCredential> {
  return post<OssCredential>(`/api/admin/config/credentials/${id}/disable`, {});
}

export async function testOssCredential(id: number): Promise<OssTestResult> {
  return post<OssTestResult>(`/api/admin/config/credentials/${id}/test`, {});
}
