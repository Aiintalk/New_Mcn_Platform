// frontend/src/types/qianchuanReview.ts

export interface ScriptEntry {
  id: string;
  title: string;
  content: string;
  source: string; // 文件名 或 'paste'
}

export interface ExcelRow {
  video_theme: string;
  spend?: string;
  impressions?: string;
  ctr?: string;
  three_sec_rate?: string;
  conversions?: string;
  cost_per_conversion?: string;
  roi?: string;
  cpm?: string;
  time_range?: string;
}

export interface GenerateRequest {
  scripts: { title: string; content: string }[];
  excel_data: ExcelRow[];
}

export interface SaveRequest {
  task_id: number;
  report: string;
  script_count: number;
  has_excel: boolean;
}

export interface OutputItem {
  id: number;
  title: string;
  created_at: string;
  preview: string;
  script_count: number | null;
  has_excel: boolean | null;
  word_count: number | null;
}

export interface OutputsResponse {
  items: OutputItem[];
  total: number;
}
