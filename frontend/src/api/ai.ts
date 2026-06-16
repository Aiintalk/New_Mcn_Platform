import { get, post, patch, del } from './request';
import type { PagedData } from '../types/api';

export interface AiStatsSummary {
  total_keys: number;
  healthy_keys: number;
  model_count: number;
  total_tokens: number;
  avg_latency_ms: number;
  service_status: 'healthy' | 'degraded' | 'overloaded' | 'unavailable';
  current_active: number;
  total_capacity: number;
}

export interface ByModelItem {
  name: string;
  tokens: number;
  pct: number;
}

export interface TokenTrendItem {
  date: string;
  input: number;
  output: number;
}

export interface AiStatsResponse {
  summary: AiStatsSummary;
  by_model: ByModelItem[];
  token_trend: TokenTrendItem[];
}

export interface AiStatsParams {
  provider?: string;
  start_date?: string;
  end_date?: string;
  [key: string]: string | undefined;
}

export interface KeyTestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  message?: string;
  error?: string;
}

export interface AiKeyRecord {
  id: number;
  label: string;
  provider: string;
  api_key: string;
  base_url: string;
  status: 'active' | 'disabled';
  concurrency: number;
  max_concurrent: number;
  total_calls: number;
  today_calls: number;
  last_tested_at: string | null;
  last_latency_ms: number | null;
}

export interface CreateAiKeyRequest {
  label: string;
  provider: string;
  api_key: string;
  base_url: string;
  max_concurrent: number;
  remark?: string;
}

export interface UpdateAiKeyRequest {
  label?: string;
  provider?: string;
  api_key?: string;
  base_url?: string;
  max_concurrent?: number;
}

export interface AiModelItem {
  id: number;
  name: string;
  model_id: string;
  provider: string;
  status: 'active' | 'inactive';
  total_calls: number;
  token_usage: number;
  last_tested_at: string | null;
  last_latency_ms: number | null;
}

export interface CreateAiModelRequest {
  name: string;
  model_id: string;
  provider: string;
}

export async function getAiKeys(): Promise<PagedData<AiKeyRecord>> {
  return get<PagedData<AiKeyRecord>>('/api/admin/ai/keys');
}

export async function getAiStats(params?: AiStatsParams): Promise<AiStatsResponse> {
  return get<AiStatsResponse>('/api/admin/ai/stats', params);
}

export async function testAiKey(id: number): Promise<KeyTestResult> {
  return post<KeyTestResult>(`/api/admin/ai/keys/${id}/test`);
}

export async function createAiKey(body: CreateAiKeyRequest): Promise<AiKeyRecord> {
  return post<AiKeyRecord>('/api/admin/ai/keys', body);
}

export async function updateAiKey(id: number, body: UpdateAiKeyRequest): Promise<AiKeyRecord> {
  return patch<AiKeyRecord>(`/api/admin/ai/keys/${id}`, body);
}

export async function deleteAiKey(id: number): Promise<void> {
  return del<void>(`/api/admin/ai/keys/${id}`);
}

export async function getAiModels(): Promise<PagedData<AiModelItem>> {
  return get<PagedData<AiModelItem>>('/api/admin/ai/models');
}

export async function createAiModel(body: CreateAiModelRequest): Promise<AiModelItem> {
  return post<AiModelItem>('/api/admin/ai/models', body);
}

export async function deleteAiModel(id: number): Promise<void> {
  return del<void>(`/api/admin/ai/models/${id}`);
}

export async function updateAiModel(id: number, body: { status: 'active' | 'inactive' }): Promise<AiModelItem> {
  return patch<AiModelItem>(`/api/admin/ai/models/${id}`, body);
}

export async function testAiModel(id: number): Promise<KeyTestResult> {
  return post<KeyTestResult>(`/api/admin/ai/models/${id}/test`);
}
