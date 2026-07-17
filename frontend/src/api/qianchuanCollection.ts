/**
 * qianchuanCollection.ts
 * 千川爆文合集工具的接口封装。
 *
 * fetch 例外说明（红线 #3）：
 *   - parseFile: FormData 上传（例外：FormData）
 *
 * 其余 JSON 接口全部走 request.ts 的 get / post / del。
 */
import { get, post, put, del } from './request';
import { useAuthStore } from '../store/authStore';
import type {
  CollectionPersona,
  ScriptListResponse,
  CreateScriptBody,
} from '../types/qianchuanCollection';

// ---------------------------------------------------------------------------
// 达人接口
// ---------------------------------------------------------------------------

/** 获取达人列表（含脚本数量） */
export function getPersonas(): Promise<{ personas: CollectionPersona[] }> {
  return get<{ personas: CollectionPersona[] }>('/api/tools/qianchuan-collection/personas');
}

/** 新建达人 */
export function createPersona(name: string): Promise<{ name: string }> {
  return post<{ name: string }>('/api/tools/qianchuan-collection/personas', { name });
}

/** 软删除达人（级联软删其下所有脚本） */
export function deletePersona(name: string): Promise<{ ok: boolean }> {
  return del<{ ok: boolean }>(`/api/tools/qianchuan-collection/personas/${encodeURIComponent(name)}`);
}

// ---------------------------------------------------------------------------
// 脚本接口
// ---------------------------------------------------------------------------

export interface GetScriptsParams {
  pool: 'global' | 'persona';
  persona_name?: string;
  q?: string;
  page?: number;
  page_size?: number;
}

/** 获取脚本列表（分页） */
export function getScripts(params: GetScriptsParams): Promise<ScriptListResponse> {
  const query = new URLSearchParams();
  query.set('pool', params.pool);
  if (params.persona_name) query.set('persona_name', params.persona_name);
  if (params.q) query.set('q', params.q);
  if (params.page) query.set('page', String(params.page));
  if (params.page_size) query.set('page_size', String(params.page_size));
  return get<ScriptListResponse>(`/api/tools/qianchuan-collection/scripts?${query.toString()}`);
}

/** 新增脚本 */
export function createScript(body: CreateScriptBody): Promise<{ id: number }> {
  return post<{ id: number }>('/api/tools/qianchuan-collection/scripts', body);
}

/** 软删除脚本 */
export function deleteScript(id: number): Promise<{ ok: boolean }> {
  return del<{ ok: boolean }>(`/api/tools/qianchuan-collection/scripts/${id}`);
}

export interface UpdateScriptBody {
  title: string;
  content: string;
  likes?: number | null;
  source?: string | null;
  source_account?: string | null;
  script_date?: string | null;
}

/** 编辑脚本 */
export function updateScript(id: number, body: UpdateScriptBody): Promise<{ ok: boolean }> {
  return put<{ ok: boolean }>(`/api/tools/qianchuan-collection/scripts/${id}`, body);
}

// ---------------------------------------------------------------------------
// 文件解析（FormData 例外，手动处理）
// ---------------------------------------------------------------------------

/** 上传文件，解析返回文本 */
export async function parseFile(file: File): Promise<{ text: string; filename: string }> {
  const token = useAuthStore.getState().token;
  const form = new FormData();
  form.append('file', file);

  const resp = await fetch('/api/tools/qianchuan-collection/parse-file', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message || err?.message || '文件解析失败');
  }
  const json = await resp.json();
  return json.data as { text: string; filename: string };
}
