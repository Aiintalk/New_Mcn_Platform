import { get, post, put } from './request';
import { useAuthStore } from '../store/authStore';
import type {
  GenerateRequest,
  SaveRequest,
  TiktokReviewConfig,
  OutputsResponse,
} from '../types/tiktokReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** SSE 流式生成复盘报告，返回原始 Response，由调用方读取 body stream */
export async function generateStream(body: GenerateRequest): Promise<Response> {
  const token = useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/tools/tiktok-review/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** 保存报告到产出中心 */
export async function saveReport(body: SaveRequest): Promise<{ output_id: number }> {
  return post<{ output_id: number }>('/api/tools/tiktok-review/save', body);
}

/** 获取历史报告列表 */
export async function getOutputs(page = 1, size = 10): Promise<OutputsResponse> {
  return get<OutputsResponse>('/api/tools/tiktok-review/outputs', { page, size });
}

/** 导出 Word，返回 Blob */
export async function exportWord(content: string, title?: string): Promise<Blob> {
  const token = useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/tiktok-review/export-word`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, title: title ?? 'TT内容复盘报告' }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `Export failed: ${resp.status}`);
  }
  return resp.blob();
}

/** 管理端：获取配置列表 */
export async function getAdminConfigs(): Promise<TiktokReviewConfig[]> {
  return get<TiktokReviewConfig[]>('/api/admin/tiktok-review/configs');
}

/** 管理端：更新配置 */
export async function updateAdminConfig(
  configKey: string,
  data: { ai_model_id: number | null; system_prompt: string | null; is_active: boolean }
): Promise<{ config_key: string }> {
  return put<{ config_key: string }>(`/api/admin/tiktok-review/configs/${configKey}`, data);
}
