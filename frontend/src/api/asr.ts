import { get, post, patch, del } from './request';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface AsrStatsOverview {
  total_calls: number;
  today_calls: number;
  avg_latency_ms: number | null;
  active_keys: number;
  total_keys: number;
}

export interface AsrOperationStat {
  operation: string; // submit / query
  calls: number;
  percentage: number; // 0-100
}

export interface AsrTrendItem {
  date: string; // "06-04"
  calls: number;
}

export interface AsrUserRank {
  user_id: number;
  username: string;
  calls: number;
}

export interface AsrStatsResponse {
  overview: AsrStatsOverview;
  operations: AsrOperationStat[];
  users: AsrUserRank[];
  trend: AsrTrendItem[];
}

export interface AsrOperationDetail {
  operation: string;
  calls: number;
  percentage: number; // 0-100
  avg_latency_ms: number | null;
  success_rate: number | null; // 0-1
}

export interface AsrUserDetail {
  user_id: number;
  username: string;
  role: string;
  calls: number;
  last_called_at: string | null;
}

export interface AsrCredential {
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
    app_key?: string;
    region?: string;
  } | null;
  last_tested_at: string | null;
  last_latency_ms: number | null;
  created_at: string;
}

export interface CreateAsrCredentialRequest {
  provider: string;
  label: string;
  api_key: string; // "access_key_id\naccess_key_secret"
  weight?: number;
  quota_limit?: number | null;
  config?: {
    app_key: string;
    region: string;
  } | null;
}

export interface UpdateAsrCredentialRequest {
  label?: string;
  status?: string;
  weight?: number;
  quota_limit?: number | null;
  config?: {
    app_key: string;
    region: string;
  } | null;
  api_key?: string;
}

export interface AsrTestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  status_text?: string;
  status_code?: number;
  error?: string;
}

// ── API functions ──────────────────────────────────────────────────────────────

export async function getAsrStats(): Promise<AsrStatsResponse> {
  return get<AsrStatsResponse>('/api/admin/asr/stats');
}

export async function getAsrOperations(): Promise<AsrOperationDetail[]> {
  const res = await get<unknown>('/api/admin/asr/operations');
  return Array.isArray(res) ? (res as AsrOperationDetail[]) : [];
}

export async function getAsrUsers(params?: {
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<{ items: AsrUserDetail[]; total: number }> {
  return get<{ items: AsrUserDetail[]; total: number }>('/api/admin/asr/users', params);
}

export async function getAsrCredentials(params?: {
  provider?: string;
  page?: number;
  page_size?: number;
}): Promise<{ items: AsrCredential[]; pagination: { page: number; page_size: number; total: number; total_pages: number } }> {
  return get<{ items: AsrCredential[]; pagination: { page: number; page_size: number; total: number; total_pages: number } }>(
    '/api/admin/config/credentials',
    params
  );
}

export async function createAsrCredential(data: CreateAsrCredentialRequest): Promise<AsrCredential> {
  return post<AsrCredential>('/api/admin/config/credentials', data);
}

export async function updateAsrCredential(id: number, data: UpdateAsrCredentialRequest): Promise<AsrCredential> {
  return patch<AsrCredential>(`/api/admin/config/credentials/${id}`, data);
}

export async function deleteAsrCredential(id: number): Promise<void> {
  return del<void>(`/api/admin/config/credentials/${id}`);
}

export async function enableAsrCredential(id: number): Promise<AsrCredential> {
  return post<AsrCredential>(`/api/admin/config/credentials/${id}/enable`, {});
}

export async function disableAsrCredential(id: number): Promise<AsrCredential> {
  return post<AsrCredential>(`/api/admin/config/credentials/${id}/disable`, {});
}

export async function testAsrCredential(id: number): Promise<AsrTestResult> {
  return post<AsrTestResult>(`/api/admin/config/credentials/${id}/test`, {});
}
