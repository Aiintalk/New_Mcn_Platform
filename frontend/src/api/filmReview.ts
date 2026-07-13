/**
 * 工作台千川成片预审接口。
 *
 * 原生 fetch 只用于视频 FormData、流式报告和文档下载；普通 JSON 保存仍走 request.ts。
 * 视频只交给平台后端，浏览器不会直接调用任何人工智能服务。
 */
import { post } from './request';
import { useAuthStore } from '../store/authStore';
import type { SaveFilmReportRequest } from '../types/filmReview';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * 后端在同一次请求中接收两条完整视频并开始分析。
 * 这是 FormData 例外：临时文件由后端和对象存储负责清理。
 */
export function analyzeFilm(original: File, edited: File): Promise<Response> {
  const form = new FormData();
  form.append('original', original);
  form.append('edited', edited);
  return fetch(`${BASE_URL}/api/tools/qianchuan-preview/analyze-video`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  });
}

/** 保存已完成的报告，进入平台产出中心。 */
export function saveFilmReport(body: SaveFilmReportRequest): Promise<{ output_id: number }> {
  return post<{ output_id: number }>('/api/tools/qianchuan-preview/save-video-report', body);
}

/** 下载报告的办公文档。 */
export async function exportFilmReport(report: string): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/api/tools/qianchuan-preview/export-word`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ content: report, title: '千川成片预审报告' }),
  });
  if (!response.ok) throw new Error('导出报告失败');
  return response.blob();
}
