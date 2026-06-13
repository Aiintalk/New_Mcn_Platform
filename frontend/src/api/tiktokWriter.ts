import { get } from './request';
import type { ChatRequest, ExportWordRequest, GetPersonasResponse } from '../types/tiktokWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** 获取有人设的达人列表 */
export const getPersonas = () =>
  get<GetPersonasResponse>('/api/tools/tiktok-writer/kols/personas');

/** AI 对话（流式，返回原始 Response，由调用方自行读取 body stream） */
export async function chatStream(body: ChatRequest): Promise<Response> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/tools/tiktok-writer/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** 导出 Word 文档，返回 Blob */
export async function exportWord(body: ExportWordRequest): Promise<Blob> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/tiktok-writer/export-word`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `Export failed: ${resp.status}`);
  }
  return resp.blob();
}

export interface TiktokWriterConfig {
  hook_eval_prompt: string;
  structure_prompt: string;
  model_id: string;
}

/** 从后端获取 hook_eval 和 structure 的 Prompt + 模型（管理端可配置）*/
export async function getTiktokWriterConfig(): Promise<TiktokWriterConfig> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/tiktok-writer/config`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`获取配置失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}
