import { useAuthStore } from '../store/authStore';
import { get, post } from './request';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const PREFIX = '/api/tools/livestream-review';

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
async function getToken() {
  return useAuthStore.getState().token;
}

export interface OutputItem {
  id: number;
  title: string;
  created_at: string;
  task_id: number | null;
}

/** 解析脚本文件（FormData 上传，原生 fetch）。FormData 例外标记 */
export async function parseFile(file: File): Promise<{ text: string; filename: string }> {
  const token = await getToken();
  const formData = new FormData();
  formData.append('file', file);
  const resp = await fetch(`${BASE_URL}${PREFIX}/parse-file`, {
    method: 'POST',
    headers: authHeaders(token),
    body: formData,
  });
  const body = await resp.json();
  if (!body.success) throw new Error(body.message ?? '文件解析失败');
  return body.data;
}

/** 流式生成复盘报告（SSE raw text，原生 fetch）。Promise<Response> 例外标记 */
export async function generateStream(payload: {
  scripts: { title: string; content: string }[];
  excel_data: Record<string, string>[];
}): Promise<Response> {
  const token = await getToken();
  return fetch(`${BASE_URL}${PREFIX}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(payload),
  });
}

/** 保存报告到产出中心 */
export const saveReport = (body: {
  task_id: number;
  report: string;
  script_count: number;
  has_excel: boolean;
}) => post<{ output_id: number }>(`${PREFIX}/save`, body);

/** 查询历史报告列表 */
export const getOutputs = (page = 1, size = 20) =>
  get<{ items: OutputItem[]; total: number }>(`${PREFIX}/outputs?page=${page}&size=${size}`);
