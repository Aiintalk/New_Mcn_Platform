import { get, post, put } from './request';
import type { ValuesWriterConfig } from '../types/valuesWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// 管理端接口
// ---------------------------------------------------------------------------

/** 获取价值观仿写配置 */
export const getConfig = () =>
  get<ValuesWriterConfig>('/api/admin/values-writer/config');

/** 更新价值观仿写配置 */
export const updateConfig = (body: Partial<ValuesWriterConfig>) =>
  put<ValuesWriterConfig>('/api/admin/values-writer/config', body);

// ---------------------------------------------------------------------------
// 运营端接口
// ---------------------------------------------------------------------------

/** 提炼达人价值观（非流式） */
export const extractValues = (kolId: number, extraContext?: string) =>
  post<{ values: string[] }>('/api/operator/values-writer/extract-values', {
    kol_id: kolId,
    ...(extraContext ? { extra_context: extraContext } : {}),
  });

/** 生成情绪方向（SSE 流式） */
export async function emotionDirectionStream(
  body: { kol_id: number; selected_values: string[]; tone?: string },
  onDelta: (text: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/operator/values-writer/emotion-direction`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `生成情绪方向失败: ${resp.status}`);
  }
  return readPlainStream(resp, onDelta);
}

/** 生成内容（SSE 流式） */
export async function writeStream(
  body: {
    kol_id: number;
    selected_values: string[];
    emotion_direction: string;
    product_context?: string;
  },
  onDelta: (text: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/operator/values-writer/write`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `生成内容失败: ${resp.status}`);
  }
  return readPlainStream(resp, onDelta);
}

/** 迭代优化（SSE 流式） */
export async function iterateStream(
  body: { kol_id: number; content: string; instruction: string },
  onDelta: (text: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/operator/values-writer/iterate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `迭代优化失败: ${resp.status}`);
  }
  return readPlainStream(resp, onDelta);
}

// ---------------------------------------------------------------------------
// 内部 helper
// ---------------------------------------------------------------------------

/** 读取 text/plain 流，累计拼接后通过 onDelta 回调 */
async function readPlainStream(
  resp: Response,
  onDelta: (full: string) => void,
): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    onDelta(full);
  }
  return full;
}
