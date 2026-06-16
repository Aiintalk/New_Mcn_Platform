import { get, post, put, del } from './request';

// ── Types ──────────────────────────────────────────────────────────────────────

export interface TikHubStatsOverview {
  total_calls: number;
  today_calls: number;
  avg_latency_ms: number;
  active_keys: number;
  total_keys: number;
}

export interface TikHubEndpointStats {
  endpoint: string;
  calls: number;
  percentage: number; // 0-100
}

export interface TikHubTrendItem {
  date: string; // "06-04"
  calls: number;
}

export interface TikHubStatsResponse {
  overview: TikHubStatsOverview;
  endpoints: TikHubEndpointStats[];
  trend: TikHubTrendItem[];
}

export interface TikHubKey {
  id: number;
  label: string;
  api_key: string;
  base_url: string;
  status: 'active' | 'inactive';
  active_requests: number;
  max_concurrent: number;
  max_users: number;
  today_calls: number;
  total_calls: number;
  last_tested_at: string | null;
  last_latency_ms: number | null;
  created_at: string;
}

export interface CreateTikHubKeyRequest {
  label: string;
  api_key: string;
  base_url: string;
  max_concurrent: number;
  max_users: number;
}

export interface UpdateTikHubKeyRequest {
  label?: string;
  max_concurrent?: number;
  max_users?: number;
}

export interface TikHubTestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  sample_nickname?: string;
  error?: string;
}

export interface TikHubEndpointDetail {
  endpoint: string;
  platform: string;
  calls: number;
  percentage: number; // 0-100
  avg_latency_ms: number;
  success_rate: number; // 0-1
}

export interface TikHubUserRank {
  user_id: number;
  username: string;
  role: string;
  calls: number;
  last_called_at: string;
}

// ── API functions ──────────────────────────────────────────────────────────────

export async function getTikHubStats(params?: {
  start_date?: string;
  end_date?: string;
}): Promise<TikHubStatsResponse> {
  return get<TikHubStatsResponse>('/api/admin/tikhub/stats', params);
}

export async function getTikHubKeys(params?: {
  status?: string;
  search?: string;
}): Promise<TikHubKey[]> {
  const res = await get<{ items: TikHubKey[] }>('/api/admin/tikhub/keys', params);
  return res.items ?? [];
}

export async function createTikHubKey(data: CreateTikHubKeyRequest): Promise<TikHubKey> {
  return post<TikHubKey>('/api/admin/tikhub/keys', data);
}

export async function updateTikHubKey(id: number, data: UpdateTikHubKeyRequest): Promise<TikHubKey> {
  return put<TikHubKey>(`/api/admin/tikhub/keys/${id}`, data);
}

export async function deleteTikHubKey(id: number): Promise<void> {
  return del<void>(`/api/admin/tikhub/keys/${id}`);
}

export async function testTikHubKey(id: number): Promise<TikHubTestResult> {
  return post<TikHubTestResult>(`/api/admin/tikhub/keys/${id}/test`);
}

export async function enableTikHubKey(id: number): Promise<void> {
  return post<void>(`/api/admin/tikhub/keys/${id}/enable`);
}

export async function disableTikHubKey(id: number): Promise<void> {
  return post<void>(`/api/admin/tikhub/keys/${id}/disable`);
}

export async function getTikHubEndpoints(): Promise<TikHubEndpointDetail[]> {
  const res = await get<unknown>('/api/admin/tikhub/endpoints');
  return Array.isArray(res) ? res : [];
}

export async function getTikHubUsers(params?: {
  start_date?: string;
  end_date?: string;
  limit?: number;
}): Promise<TikHubUserRank[]> {
  const res = await get<{ items: TikHubUserRank[] }>('/api/admin/tikhub/users', params);
  return res.items ?? [];
}
