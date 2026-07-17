import { get, post, put, del } from './request';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface KolListItem {
  id: number;
  name: string;
  account_name: string | null;
  category: string | null;
  follower_count: number | null;
  has_persona: boolean;
  has_content_plan: boolean;
  reference_count: number;
  has_intake: boolean;
  updated_at: string | null;
}

export interface MaterialLibraryPagination {
  page: number;
  page_size: number;
  total: number;
}

export interface MaterialLibraryKolList {
  items: KolListItem[];
  pagination: MaterialLibraryPagination;
}

export type MaterialLibraryKolsResponse = KolListItem[] | MaterialLibraryKolList;

/** 兼容旧数组响应和当前分页响应，页面只需使用红人数据项。 */
export function materialLibraryKolItems(response: MaterialLibraryKolsResponse): KolListItem[] {
  return Array.isArray(response) ? response : response.items;
}

export interface KolReference {
  id: number;
  title: string;
  likes: number | null;
  source: string;
  type: string;
  content: string;
  data_description: string | null;
  document_name: string | null;
  document_type: string | null;
  document_size: number | null;
  has_video: boolean;
  video_name: string | null;
  video_content_type: string | null;
  video_size: number | null;
  created_at: string | null;
}

export interface KolDetail {
  id: number;
  name: string;
  account_name: string | null;
  category: string | null;
  follower_count: number | null;
  persona: string;
  content_plan: string;
  references: Record<string, KolReference[]>;
}

/**
 * 素材详情当前按分类分组返回；兼容后端改为列表或分页列表时的页面读取，
 * 让工作台始终只展示当前红人的素材。
 */
export function flattenKolReferences(
  references: Record<string, KolReference[]> | KolReference[] | { items: KolReference[] },
): KolReference[] {
  if (Array.isArray(references)) return references;
  if ('items' in references) return references.items;
  return Object.values(references).flat();
}

export interface IntakeData {
  source: string;
  messages: unknown[];
  ai_report: string | null;
  report_status: string;
  created_at: string | null;
}

export interface MaterialLibraryConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string;
  is_active: boolean;
  updated_at: string | null;
}

// ---------------------------------------------------------------------------
// Operator API
// ---------------------------------------------------------------------------

export const getMaterialLibraryKols = (search?: string) =>
  get<MaterialLibraryKolsResponse>('/api/tools/material-library/kols', { search });

export const getMaterialLibraryKolDetail = (kolId: number) =>
  get<KolDetail>(`/api/tools/material-library/kols/${kolId}`);

export const updateKolProfile = (kolId: number, data: { persona?: string; content_plan?: string }) =>
  put(`/api/tools/material-library/kols/${kolId}/profile`, data);

export const createKolReference = (
  kolId: number,
  data: {
    title: string;
    likes?: number;
    source?: string;
    type: string;
    content: string;
    data_description?: string;
    document_name?: string;
    document_type?: string;
    document_size?: number;
  },
) => post<KolReference>(`/api/tools/material-library/kols/${kolId}/references`, data);

export const updateKolReference = (
  kolId: number,
  refId: number,
  data: {
    title?: string;
    data_description?: string;
    content?: string;
    document_name?: string;
    document_type?: string;
    document_size?: number;
  },
) => put<KolReference>(`/api/tools/material-library/kols/${kolId}/references/${refId}`, data);

export const deleteKolReference = (kolId: number, refId: number) =>
  del(`/api/tools/material-library/kols/${kolId}/references/${refId}`);

export interface ParsedKolReferenceDocument {
  text: string;
  document_name: string;
  document_type: string | null;
  document_size: number;
}

async function uploadMaterialFile<T>(path: string, file: File): Promise<T> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  const body = await response.json().catch(() => null) as {
    success?: boolean;
    message?: string;
    data?: T;
  } | null;
  if (!response.ok || !body?.success) {
    throw new Error(body?.message ?? `上传失败：${response.status}`);
  }
  return body.data as T;
}

/** 上传脚本文档并返回可在保存前修改的解析正文。 */
export const parseKolReferenceDocument = (kolId: number, file: File) =>
  uploadMaterialFile<ParsedKolReferenceDocument>(
    `/api/tools/material-library/kols/${kolId}/references/parse-document`, file,
  );

/** 上传视频；已有视频时仅在运营明确选择新文件后调用，服务端会替换旧对象。 */
export const uploadKolReferenceVideo = (kolId: number, refId: number, file: File) =>
  uploadMaterialFile<KolReference>(
    `/api/tools/material-library/kols/${kolId}/references/${refId}/video`, file,
  );

/** 只在展开含视频的素材时获取后端签发的短时播放地址。 */
export const getKolReferenceVideoPlayback = (kolId: number, refId: number) =>
  get<{ url: string; expires_in: number }>(
    `/api/tools/material-library/kols/${kolId}/references/${refId}/video/playback`,
  );

export const getKolIntake = (kolId: number) =>
  get<IntakeData | null>(`/api/tools/material-library/kols/${kolId}/intake`);

export const generateSoul = (kolId: number) =>
  post<{ soul_md: string }>(`/api/tools/material-library/kols/${kolId}/generate-soul`);

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

export const getMaterialLibraryConfigs = () =>
  get<MaterialLibraryConfig[]>('/api/admin/material-library/configs');

export const updateMaterialLibraryConfig = (data: {
  ai_model_id?: number;
  system_prompt?: string;
  is_active?: boolean;
}) => put<MaterialLibraryConfig>('/api/admin/material-library/configs', data);
