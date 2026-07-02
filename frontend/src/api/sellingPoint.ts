import { del, get, post, put } from './request';
import type { HistoryItem, HistoryRecord, SellingPointConfig, UploadedFile } from '../types/sellingPoint';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const PREFIX = '/api/tools/selling-point-extractor';

async function getToken(): Promise<string | null> {
  return (await import('../store/authStore')).useAuthStore.getState().token;
}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** AI 流式对话（后端从 DB 读取 Prompt，前端只传 messages）。流式必须走原生 fetch。 */
export async function chatStream(messages: Array<{ role: string; content: string }>): Promise<Response> {
  const token = await getToken();
  return fetch(`${BASE_URL}${PREFIX}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify({ messages }),
  });
}

/** 解析上传文件（FormData 无法走 request.ts 的 JSON 封装，保留原生 fetch + 手动解包 .data） */
export async function parseFile(file: File): Promise<{ text: string; filename: string }> {
  const token = await getToken();
  const formData = new FormData();
  formData.append('file', file);
  const resp = await fetch(`${BASE_URL}${PREFIX}/parse-file`, {
    method: 'POST',
    headers: authHeaders(token),
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? err?.message ?? `文件解析失败 (${resp.status})`);
  }
  const body = await resp.json();
  return body.data;
}

/** 获取历史列表 */
export const getHistoryList = () =>
  get<{ records: HistoryItem[] }>(`${PREFIX}/history`);

/** 获取单条历史 */
export const getHistoryRecord = (id: string) =>
  get<{ record: HistoryRecord }>(`${PREFIX}/history`, { id });

/** 保存历史记录 */
export const saveHistory = (body: {
  productName: string;
  result: string;
  chatHistory: Array<{ role: string; content: string }>;
  briefFiles: UploadedFile[];
  scriptFiles: UploadedFile[];
}) =>
  post<{ id: string }>(`${PREFIX}/history`, body);

/** 软删除历史记录 */
export const deleteHistoryRecord = (id: string) =>
  del<null>(`${PREFIX}/history?id=${id}`);

// -- Admin API --

export const getAdminSellingPointConfigs = () =>
  get<{ success: boolean; data: SellingPointConfig[] }>('/api/admin/selling-point/configs');

export const updateAdminSellingPointConfig = (
  key: string,
  data: { ai_model_id?: number | null; system_prompt?: string; is_active?: boolean }
) =>
  put<null>(`/api/admin/selling-point/configs/${key}`, data);
