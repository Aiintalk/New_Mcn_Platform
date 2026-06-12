import { get, post, put } from './request';
import type { FetchResult, BenchmarkAnalysis, BenchmarkConfig } from '../types/benchmark';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// -- Operator API --

export const fetchAccount = (input: string) =>
  post<FetchResult>('/api/operator/benchmark/fetch', { input });

/** AI 分析（返回原始 Response，前端自行解析 SSE 流） */
export async function analyzeStream(body: {
  account_name?: string;
  sec_user_id?: string;
  top10_content: string;
  recent30_content: string;
}): Promise<Response> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/operator/benchmark/analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

export const getMyHistory = () =>
  get<BenchmarkAnalysis[]>('/api/operator/benchmark/history');

export const getHistoryDetail = (id: number) =>
  get<BenchmarkAnalysis>(`/api/operator/benchmark/history/${id}`);

// -- Admin API --

export const getAdminConfigs = () =>
  get<BenchmarkConfig[]>('/api/admin/benchmark/configs');

export const updateAdminConfig = (key: string, data: { ai_model_id?: number; system_prompt?: string; is_active?: boolean }) =>
  put<null>(`/api/admin/benchmark/configs/${key}`, data);

export const getAdminAnalyses = () =>
  get<BenchmarkAnalysis[]>('/api/admin/benchmark/analyses');

export const getAdminAnalysisDetail = (id: number) =>
  get<BenchmarkAnalysis>(`/api/admin/benchmark/analyses/${id}`);

export const regenerateAnalysis = (id: number) =>
  post<null>(`/api/admin/benchmark/analyses/${id}/regenerate`, {});
