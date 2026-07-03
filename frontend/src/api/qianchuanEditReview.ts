/**
 * qianchuanEditReview.ts
 * 千川剪辑预审工具的接口封装。
 *
 * fetch 例外说明（红线 #3）：
 *   - extractFrames: FormData 上传
 *   - transcribeVideo: FormData 上传
 *   - chatStream: SSE 流式（getReader）
 *   - exportWord: Blob 下载（.blob()）
 *   - saveOutput: 走 request.ts（标准 JSON）
 *   - getConfig: 走 request.ts（标准 JSON）
 */
import { get, post } from './request'
import { useAuthStore } from '../store/authStore'

export interface Frame {
  time: number
  base64: string
}

export interface ExtractFramesResult {
  frames: Frame[]
  duration: number
}

export interface SaveOutputBody {
  title: string
  report: string
  original_duration: number
  ours_duration: number
  original_frame_count: number
  ours_frame_count: number
}

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** 截帧：FormData 上传，原生 fetch（例外：FormData）*/
export async function extractFrames(file: File, count = 8): Promise<ExtractFramesResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('count', String(count))

  const resp = await fetch('/api/tools/extract-frames', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.message || '截帧失败')
  }
  const json = await resp.json()
  return json.data
}

/** 转录：FormData 上传，原生 fetch（例外：FormData）*/
export async function transcribeVideo(file: File, language = 'zh'): Promise<{ text: string }> {
  const form = new FormData()
  form.append('file', file)
  form.append('language', language)

  const resp = await fetch('/api/tools/transcribe', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: form,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error(err?.message || '转录失败')
  }
  const json = await resp.json()
  return json.data
}

/** 流式预审：原生 fetch + getReader（例外：getReader）*/
export function chatStream(
  messages: Array<{ role: string; content: unknown }>,
  systemPrompt: string,
  model = 'gpt-4o',
  maxTokens = 8000,
  aiModelId?: number | null,
): Promise<Response> {
  return fetch('/api/tools/chat-stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      messages,
      system_prompt: systemPrompt,
      model,
      max_tokens: maxTokens,
      ...(aiModelId ? { ai_model_id: aiModelId } : {}),
    }),
  })
}

/** 导出 Word：Blob 下载，原生 fetch（例外：.blob()）*/
export async function exportWord(content: string, title = '千川剪辑预审报告'): Promise<Blob> {
  const resp = await fetch('/api/tools/export-word', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ content, title }),
  })
  if (!resp.ok) throw new Error('导出失败')
  return resp.blob()
}

/** 保存报告：标准 JSON，走 request.ts（红线 #3）*/
export function saveOutput(body: SaveOutputBody): Promise<{ id: number; created_at: string }> {
  return post<{ id: number; created_at: string }>('/api/tools/qianchuan-edit-review/outputs', body)
}

/** 获取管理端配置（system_prompt / ai_model_id），未配置返回 null；走 request.ts（红线 #3）*/
export function getConfig(): Promise<{ system_prompt: string | null; ai_model_id: number | null }> {
  return get<{ system_prompt: string | null; ai_model_id: number | null }>(
    '/api/tools/qianchuan-edit-review/config'
  )
}
