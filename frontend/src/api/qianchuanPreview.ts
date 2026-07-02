/**
 * qianchuanPreview.ts
 * 千川文案预审工具的接口封装。
 *
 * fetch 例外说明（红线 #3）：
 *   - parseFile: FormData 上传（例外：FormData）
 *   - chatStream: SSE 流式（例外：getReader）
 *   - exportWord: Blob 下载（例外：.blob()）
 */
import { useAuthStore } from '../store/authStore';
import type { ParseFileResponse } from '../types/qianchuanPreview';

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 解析文案文件（FormData 例外，手动处理）*/
export async function parseFile(file: File): Promise<ParseFileResponse> {
  const form = new FormData();
  form.append('file', file);

  const resp = await fetch('/api/tools/qianchuan-preview/parse-file', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.message || '文件解析失败');
  }
  const json = await resp.json();
  return json.data as ParseFileResponse;
}

/** 流式生成预审报告（SSE 例外，原生 fetch + getReader）*/
export function chatStream(scriptA: string, scriptB: string): Promise<Response> {
  return fetch('/api/tools/qianchuan-preview/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ script_a: scriptA, script_b: scriptB }),
  });
}

/** 导出 Word（Blob 下载例外，原生 fetch + .blob()）*/
export async function exportWord(content: string, title = '千川文案预审报告'): Promise<Blob> {
  const resp = await fetch('/api/tools/qianchuan-preview/export-word', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ content, title }),
  });
  if (!resp.ok) throw new Error('导出失败');
  return resp.blob();
}
