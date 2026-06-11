export interface UploadedFile {
  name: string;
  text: string;
  status: 'uploading' | 'done' | 'error';
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
}

export interface KolSubmission {
  id: number;
  nickname: string;
  submitted_at: string;
  formatted_answers: string;
  report: string;
}

export type PersonaStep = 1 | 2 | 3;
export type PersonaTab = 'profile' | 'plan';
