import { get, post, del } from './request';
import type { RetrospectiveSession, RetrospectiveConfig } from '../types/retrospective';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// 管理端接口
// ---------------------------------------------------------------------------

/** 获取复盘配置 */
export const getConfig = () =>
  get<RetrospectiveConfig>('/api/admin/retrospective/config');

/** 更新复盘配置 */
export const updateConfig = (body: Partial<RetrospectiveConfig>) =>
  post<RetrospectiveConfig>('/api/admin/retrospective/config', body);

// ---------------------------------------------------------------------------
// 运营端接口
// ---------------------------------------------------------------------------

/** 获取复盘会话列表 */
export const getSessions = (kolId: number, page = 1) =>
  get<{ items: RetrospectiveSession[]; pagination: { page: number; page_size: number; total: number; total_pages: number } }>(
    `/api/operator/workspace/${kolId}/retrospective`,
    { page, page_size: 20 },
  );

/** 保存复盘会话（新建/更新） */
export const saveSession = (kolId: number, data: Partial<RetrospectiveSession>) =>
  post<RetrospectiveSession>(`/api/operator/workspace/${kolId}/retrospective`, data);

/** 删除复盘会话 */
export const deleteSession = (kolId: number, id: number) =>
  del<{ id: number }>(`/api/operator/workspace/${kolId}/retrospective/${id}`);

/** 上传并解析文件，返回提取的文本 */
export const parseFiles = async (kolId: number, files: File[]): Promise<{ text: string }> => {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  const resp = await fetch(`${BASE_URL}/api/operator/workspace/${kolId}/retrospective/parse-files`, {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: fd,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message ?? `文件解析失败: ${resp.status}`);
  }
  const json = await resp.json();
  return json.data as { text: string };
};

/** 流式分析复盘（SSE），onDelta 每次收到累积全文 */
export async function analyzeStream(
  kolId: number,
  sessionId: number,
  onDelta: (text: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(
    `${BASE_URL}/api/operator/workspace/${kolId}/retrospective/${sessionId}/analyze`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    },
  );
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `分析失败: ${resp.status}`);
  }
  return readPlainStream(resp, onDelta);
}

/** 导出复盘结果为 Word，返回 Blob */
export const exportWord = async (kolId: number, sessionId: number): Promise<Blob> => {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const resp = await fetch(
    `${BASE_URL}/api/operator/workspace/${kolId}/retrospective/${sessionId}/export-word`,
    {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    },
  );
  if (!resp.ok) {
    throw new Error(`导出失败: ${resp.status}`);
  }
  return resp.blob();
};

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
