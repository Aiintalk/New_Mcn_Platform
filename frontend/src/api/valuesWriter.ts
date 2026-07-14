import { get, post, put } from './request';
import type { ValuesWriterConfig, ValuesWriterSaveOutputRequest } from '../types/valuesWriter';

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

/** 保存价值观仿写产出至历史（手动保存） */
export const saveOutput = (body: ValuesWriterSaveOutputRequest) =>
  post<{ output_id: number }>('/api/operator/values-writer/save-output', body);

export interface EmotionDirection {
  type: '焦虑型' | '诱惑型';
  title: string;
  description: string;
  anchor: string;
}

/** 旧版四步流程第三步：服务端读取当前商品和完整红人档案。 */
export const deriveDirections = (body: {
  kol_id: number;
  opening_line: string;
  original_script: string;
}) => post<{ directions: EmotionDirection[] }>('/api/operator/values-writer/derive-directions', body);

/** 旧版四步流程第四步：流式返回 analysis/rewrite/report 三段结构。 */
export async function generateValueScript(
  body: {
    kol_id: number;
    opening_line: string;
    original_script: string;
    direction: EmotionDirection;
  },
  onDelta: (text: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/operator/values-writer/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `生成脚本失败: ${resp.status}`);
  }
  return readSseStream(resp, onDelta);
}

/** 旧版结果页人工修改：流式返回新的 analysis/rewrite/report 三段结构。 */
export async function iterateValueScript(
  body: {
    kol_id: number;
    opening_line: string;
    original_script: string;
    direction: EmotionDirection;
    current_result: { analysis: string; rewrite: string; report: string };
    instruction: string;
    history: Array<{ instruction: string; result: { analysis: string; rewrite: string; report: string } }>;
  },
  onDelta: (text: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/operator/values-writer/iterate-structured`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `修改脚本失败: ${resp.status}`);
  }
  return readSseStream(resp, onDelta);
}

async function readSseStream(resp: Response, onDelta: (text: string) => void): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const events = buffer.split('\n\n');
    buffer = events.pop() ?? '';
    for (const event of events) {
      const line = event.split('\n').find((item) => item.startsWith('data: '));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as { delta?: string; done?: boolean };
      if (payload.delta) {
        full += payload.delta;
        onDelta(full);
      }
    }
    if (done) break;
  }
  if (full.startsWith('[ERROR]')) {
    throw new Error(full.replace(/^\[ERROR\]\s*/, ''));
  }
  return full;
}

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
