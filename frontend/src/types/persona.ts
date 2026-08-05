export interface UploadedFile {
  name: string;
  text: string;
  status: 'uploading' | 'done' | 'error';
  source?: 'manual' | 'intake';
  kolId?: number;
}

export interface FetchDouyinResult {
  nickname: string;
  sec_user_id: string;
  total_videos: number;
  top10_count: number;
  recent30_count: number;
  top10_text: string;
  recent30_text: string;
}

export interface PersonaReport {
  id: number;
  kol_id: number | null;
  influencer_name: string | null;
  douyin_nickname: string | null;
  status: 'pending' | 'generating' | 'ready' | 'failed';
  created_at: string;
}

export interface PersonaReportDetail extends PersonaReport {
  douyin_id: string | null;
  profile_result: string | null;
  plan_result: string | null;
  raw_output: string | null;
  generated_at: string | null;
  sync_result: Record<PersonaSyncField, PersonaSyncAction>;
  pending_overwrites: PersonaPendingOverwrite[];
  failure_reason?: 'kol_deleted' | 'generation_failed' | null;
  positioning_sync_failed?: boolean;
  fact_sync_failed?: boolean;
}

export interface PersonaKol {
  id: number;
  name: string;
  account_name: string | null;
  douyin_id: string | null;
  profile_filled_count: number;
  profile_total: number;
}

export interface PersonaKolList {
  items: PersonaKol[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export interface PersonaKolIntake {
  completed_at: string | null;
  formatted_answers: string;
  report: string;
}

export type PersonaSyncField = 'persona' | 'content_plan';
export type PersonaSyncDecision = 'keep' | 'overwrite';
export type PersonaSyncAction = 'auto_written' | 'pending' | 'overwritten' | 'kept' | 'unchanged';

export interface PersonaPendingOverwrite {
  field: PersonaSyncField;
  current_summary: string;
  report_summary: string;
}

export interface PersonaSyncDecisionResult {
  report_id: number;
  fields: Record<PersonaSyncField, PersonaSyncAction>;
}

export type PersonaStep = 1 | 2 | 3;
export type PersonaTab = 'profile' | 'plan';
