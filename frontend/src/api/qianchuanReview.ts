// frontend/src/api/qianchuanReview.ts
import type { GenerateRequest, OutputsResponse, SaveRequest } from '../types/qianchuanReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const PREFIX = '/api/tools/qianchuan-review';

async function getToken(): Promise<string | null> {
  return (await import('../store/authStore')).useAuthStore.getState().token;
}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 解析上传的脚本文件 */
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
    throw new Error(err?.message ?? `解析失败: ${resp.status}`);
  }
  const data = await resp.json();
  return data.data;
}

/** SSE 流式生成复盘报告，返回 Response（供调用方读取流 + X-Task-Id header） */
export async function generateReport(payload: GenerateRequest): Promise<Response> {
  const token = await getToken();
  return fetch(`${BASE_URL}${PREFIX}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(payload),
  });
}

/** 保存报告到产出中心 */
export async function saveReport(payload: SaveRequest): Promise<{ output_id: number }> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}${PREFIX}/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`保存失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}

/** 查询历史复盘报告列表 */
export async function getOutputs(page = 1, size = 10): Promise<OutputsResponse> {
  const token = await getToken();
  const resp = await fetch(`${BASE_URL}${PREFIX}/outputs?page=${page}&size=${size}`, {
    headers: authHeaders(token),
  });
  if (!resp.ok) throw new Error(`获取历史失败: ${resp.status}`);
  const data = await resp.json();
  return data.data;
}
