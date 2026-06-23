import { get, post, put } from './request';
import type {
  QianchuanWriterPersona,
  QianchuanWriterConfig,
  QianchuanOutputsPage,
  QianchuanChatRequest,
  QianchuanSaveOutputRequest,
  QianchuanExportWordRequest,
  QianchuanParseFileResult,
} from '../types/qianchuanWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// 运营端 6 个接口
// ---------------------------------------------------------------------------

/** Step 1：获取有人设的达人列表 */
export const getPersonas = () =>
  get<QianchuanWriterPersona[]>('/api/tools/qianchuan-writer/kols/personas');

/** Step 2：文件解析（FormData，例外不走 request.ts） */
export async function parseFile(file: File): Promise<QianchuanParseFileResult> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const formData = new FormData();
  formData.append('file', file);
  const resp = await fetch(`${BASE_URL}/api/tools/qianchuan-writer/parse-file`, {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `文件解析失败: ${resp.status}`);
  }
  const body = await resp.json();
  if (!body.success) {
    throw new Error(body.message ?? '文件解析失败');
  }
  return body.data as QianchuanParseFileResult;
}

/** Step 4：AI 流式对话（SSE 例外，返回原始 Response） */
export async function chatStream(body: QianchuanChatRequest): Promise<Response> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  return fetch(`${BASE_URL}/api/tools/qianchuan-writer/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
}

/** Step 4：保存仿写产出 */
export async function saveOutput(body: QianchuanSaveOutputRequest): Promise<{ output_id: number }> {
  return post<{ output_id: number }>('/api/tools/qianchuan-writer/save-output', body);
}

/** Step 4：导出 Word 文档（Blob 例外） */
export async function exportWord(body: QianchuanExportWordRequest): Promise<Blob> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/qianchuan-writer/export-word`, {
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

/** 历史记录列表 */
export const getOutputs = (page: number, pageSize: number = 20) =>
  get<QianchuanOutputsPage>('/api/tools/qianchuan-writer/outputs', {
    page,
    page_size: pageSize,
  });

// ---------------------------------------------------------------------------
// 管理端 2 个接口
// ---------------------------------------------------------------------------

/** 管理端：获取配置列表 */
export const getConfigs = () =>
  get<QianchuanWriterConfig[]>('/api/admin/qianchuan-writer/configs');

/** 管理端：更新配置 */
export const updateConfig = (configKey: string, payload: {
  ai_model_id?: number | null;
  system_prompt?: string | null;
  is_active?: boolean;
}) => put<{ config_key: string }>(`/api/admin/qianchuan-writer/configs/${configKey}`, payload);
