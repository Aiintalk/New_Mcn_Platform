import { get, post, del } from './request';
import { useAuthStore } from '../store/authStore';
import type { FetchDouyinResult, PersonaReport, PersonaReportDetail, KolSubmission } from '../types/persona';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
const API = '/api/persona';          // 给 request.ts 封装用的（内部已拼 BASE_URL）
const FETCH_BASE = `${BASE_URL}/api/persona`;  // 给原生 fetch 用的（需要完整地址）

// ── 抖音号解析 ──────────────────────────────────────────────────

export const fetchDouyin = (url: string) =>
  post<FetchDouyinResult>(`${API}/fetch-douyin`, { url });

// ── 文件解析 ────────────────────────────────────────────────────

export async function parseFile(file: File): Promise<{ text: string }> {
  const token = useAuthStore.getState().token;
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${FETCH_BASE}/parse-file`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) throw new Error('文件解析失败');
  const json = await res.json();
  return json.data;
}

// ── 问卷模板下载 ────────────────────────────────────────────────

export async function downloadQuestionnaireTemplate(): Promise<void> {
  const token = useAuthStore.getState().token;
  const res = await fetch(`${FETCH_BASE}/questionnaire-template`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error('下载失败');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = '达人入职信息采集表.docx';
  a.click();
  URL.revokeObjectURL(url);
}

// ── SSE 流式生成 ────────────────────────────────────────────────

export interface GenerateParams {
  influencer_info: string;
  top10_content?: string;
  supplement_text?: string;
  benchmark_text?: string;
  douyin_id?: string;
  douyin_nickname?: string;
  recent30_text?: string;
  questionnaire_files?: Array<{ filename: string; text: string }>;
  supplement_files?: Array<{ filename: string; text: string }>;
  benchmark_profile_files?: Array<{ filename: string; text: string }>;
  benchmark_plan_files?: Array<{ filename: string; text: string }>;
}

export async function generatePersona(
  params: GenerateParams,
  signal?: AbortSignal,
): Promise<{ reader: ReadableStreamDefaultReader<Uint8Array>; reportId: number | null }> {
  const token = useAuthStore.getState().token;
  const res = await fetch(`${FETCH_BASE}/generate`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(params),
    signal,
  });
  if (!res.ok) throw new Error('生成请求失败');
  const reportId = res.headers.get('X-Report-Id');
  const reader = res.body!.getReader();
  return { reader, reportId: reportId ? Number(reportId) : null };
}

// ── SSE 流式优化对话 ────────────────────────────────────────────

export interface OptimizeParams {
  messages: Array<{ role: 'user' | 'assistant'; content: string }>;
  current_content: string;
  content_type: 'profile' | 'plan';
  influencer_info: string;
  benchmark_text?: string;
}

export async function optimizePersona(
  params: OptimizeParams,
  signal?: AbortSignal,
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const token = useAuthStore.getState().token;
  const res = await fetch(`${FETCH_BASE}/optimize`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(params),
    signal,
  });
  if (!res.ok) throw new Error('优化请求失败');
  return res.body!.getReader();
}

// ── 导出 Word ───────────────────────────────────────────────────

export async function exportPersonaWord(params: {
  report_id: number;
  type: 'profile' | 'plan';
}): Promise<void> {
  const token = useAuthStore.getState().token;
  const res = await fetch(`${FETCH_BASE}/export-word`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('导出失败');
  const blob = await res.blob();
  const typeLabel = params.type === 'profile' ? '人格档案' : '内容规划';
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*=UTF-8''(.+)/);
  const filename = match ? decodeURIComponent(match[1]) : `${typeLabel}_${date}.docx`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── KOL 入驻列表 ────────────────────────────────────────────────

export const getKolSubmissions = () =>
  get<KolSubmission[]>(`${API}/kol-submissions`);

// ── 报告列表 / 详情 / 删除 ──────────────────────────────────────

export const getPersonaReports = () =>
  get<PersonaReport[]>(`${API}/reports`);

export const getPersonaReportDetail = (id: number) =>
  get<PersonaReportDetail>(`${API}/reports/${id}`);

export const deletePersonaReport = (id: number) =>
  del<{ deleted: boolean }>(`${API}/reports/${id}`);
