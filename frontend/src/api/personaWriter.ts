import { get, post, put } from './request';
import type {
  PersonaWriterPersona,
  PersonaWriterConfig,
  PersonaWriterOutputsPage,
  PersonaWriterOutput,
  PersonaChatRequest,
  PersonaChatMessage,
  PersonaSaveOutputRequest,
  PersonaExportWordRequest,
  FetchVideoResult,
} from '../types/personaWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// 运营端 8 个接口
// ---------------------------------------------------------------------------

/** Step 1：获取有人设的达人列表 */
export const getPersonas = () =>
  get<PersonaWriterPersona[]>('/api/tools/persona-writer/kols/personas');

/** Step 2.1：抖音分享链接解析（标准 JSON 信封） */
export function fetchVideo(share_url: string): Promise<FetchVideoResult> {
  return post<FetchVideoResult>('/api/tools/persona-writer/fetch-video', { share_url });
}

/** Step 2.4：AI 开头评估（text/plain 流式，getReader 模式，例外走 fetch） */
export async function evaluateOpeningStream(
  transcript: string,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/tools/persona-writer/evaluate-opening`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ transcript }),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message ?? `评估失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

/** Step 3.1：AI 结构拆解（text/plain 流式，getReader 模式，例外走 fetch） */
export async function analyzeStructureStream(
  transcript: string,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/tools/persona-writer/analyze-structure`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ transcript }),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message ?? `拆解失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

/** Step 3.3/3.4：AI 写作 + 多轮追问（text/plain 流式，getReader 模式，例外走 fetch） */
export async function chatStream(
  body: PersonaChatRequest,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/tools/persona-writer/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message ?? `生成失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

/** Step 3.5：保存产出（标准 JSON 信封） */
export function saveOutput(
  body: PersonaSaveOutputRequest,
): Promise<{ output_id: number }> {
  return post<{ output_id: number }>('/api/tools/persona-writer/save-output', body);
}

/** Step 3.6：导出 Word 文档（Blob 例外） */
export async function exportWord(body: PersonaExportWordRequest): Promise<Blob> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/persona-writer/export-word`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `导出失败: ${resp.status}`);
  }
  return resp.blob();
}

/** 历史记录列表（账号隔离） */
export function getOutputs(
  page: number,
  pageSize: number = 20,
): Promise<PersonaWriterOutputsPage> {
  return get<PersonaWriterOutputsPage>('/api/tools/persona-writer/outputs', {
    page,
    page_size: pageSize,
  });
}

// ---------------------------------------------------------------------------
// 管理端 2 个接口
// ---------------------------------------------------------------------------

/** 管理端：获取配置列表 */
export const getConfigs = () =>
  get<PersonaWriterConfig[]>('/api/admin/persona-writer/configs');

/** 管理端：更新配置（4 Prompt + 2 模型 + 启用） */
export function updateConfig(
  configKey: string,
  payload: {
    evaluation_prompt?: string | null;
    analysis_prompt?: string | null;
    writing_prompt?: string | null;
    iteration_prompt?: string | null;
    light_model_id?: number | null;
    heavy_model_id?: number | null;
    is_active?: boolean;
  },
): Promise<{ config_key: string }> {
  return put<{ config_key: string }>(
    `/api/admin/persona-writer/configs/${configKey}`,
    payload,
  );
}

// ---------------------------------------------------------------------------
// 内部 helper
// ---------------------------------------------------------------------------

/** 读取 text/plain 流，累计拼接后通过 onChunk 回调 */
async function readPlainStream(
  resp: Response,
  onChunk: (full: string) => void,
): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    onChunk(full);
  }
  return full;
}

/** 导出仅用于类型引用的别名，避免 qianchuan-writer 混淆 */
export type { PersonaChatMessage, PersonaWriterOutput };
