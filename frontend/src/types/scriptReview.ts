export type ScriptType = 'direct' | 'value';
export type ReviewRating = 'pass' | 'minor' | 'fail';

export interface MustFixItem {
  type: string;
  quote: string;
  fix: string;
}

export interface ReviewResult {
  rating: ReviewRating;
  must_fix: MustFixItem[];
  suggestions: string[];
  passed: string[];
}

export interface ScriptReviewConfig {
  id: number;
  config_key: string;
  direct_prompt: string | null;
  value_prompt: string | null;
  ai_model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}

export interface ReviewRequest {
  script_type: ScriptType;
  original_script: string;
  adapted_script: string;
  product?: {
    nickname?: string;
    mechanism?: string;
    core_selling_point?: string;
  } | null;
}
