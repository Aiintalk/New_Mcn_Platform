// src/types/retrospective.ts

export type SessionStatus = 'draft' | 'done';

export interface RetrospectiveSession {
  id: number;
  kol_id: number;
  title: string;
  status: SessionStatus;
  live_data: string | null;
  material_data: string | null;
  review_text: string | null;
  live_script: string | null;
  material_scripts: { name: string; text: string }[] | null;
  result: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RetrospectiveConfig {
  id: number;
  config_key: string;
  system_prompt: string | null;
  ai_model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}
