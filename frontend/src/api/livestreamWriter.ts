import { get } from './request';
import type { ChatRequest, LivestreamWriterConfig, ParseFileResponse, Persona } from '../types/livestreamWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/** 从后端实时拉取 Prompt + 模型配置（管理端可修改） */
export async function getLivestreamWriterConfig(): Promise<LivestreamWriterConfig> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/livestream-writer/config`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`获取配置失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}

/** 获取 content_plan 和 persona 均非空的达人列表 */
export const getKolPersonas = () =>
  get<{ personas: Persona[] }>('/api/tools/livestream-writer/kols/personas');

/** 文件解析（FormData 上传，例外：使用原生 fetch） */
export async function parseFile(file: File): Promise<ParseFileResponse> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  const formData = new FormData();
  formData.append('file', file);
  const resp = await fetch(`${BASE_URL}/api/tools/livestream-writer/parse-file`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message ?? `文件解析失败: ${resp.status}`);
  }
  const data = await resp.json();
  return data.data;
}

/** AI 流式对话（返回原始 Response，调用方读取 body stream） */
export async function chatStream(body: ChatRequest): Promise<Response> {
  const token = (await import('../store/authStore')).useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/tools/livestream-writer/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}
