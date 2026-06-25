import { get, post, put, del } from './request';

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

export interface KolReference {
  id: number;
  title: string;
  likes: number | null;
  source: string;
  content: string;
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
  get<KolListItem[]>('/api/tools/material-library/kols', { search });

export const getMaterialLibraryKolDetail = (kolId: number) =>
  get<KolDetail>(`/api/tools/material-library/kols/${kolId}`);

export const updateKolProfile = (kolId: number, data: { persona?: string; content_plan?: string }) =>
  put(`/api/tools/material-library/kols/${kolId}/profile`, data);

export const createKolReference = (
  kolId: number,
  data: { title: string; likes?: number; source?: string; type: string; content: string },
) => post<KolReference>(`/api/tools/material-library/kols/${kolId}/references`, data);

export const deleteKolReference = (kolId: number, refId: number) =>
  del(`/api/tools/material-library/kols/${kolId}/references/${refId}`);

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
