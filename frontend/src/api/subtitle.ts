import { get, post, put } from './request';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExtractResult {
  text: string;
  title: string;
  audio_url: string;
}

export interface ExtractRequest {
  share_text?: string;
  file_url?: string;
}

export interface MindmapBranch {
  title: string;
  children: string[];
}

export interface MindmapResult {
  rootTitle: string;
  summary: string;
  branches: MindmapBranch[];
}

export interface SubtitleConfig {
  id: number;
  config_key: string;
  mindmap_model_id: number | null;
  mindmap_prompt: string;
  is_active: boolean;
  updated_at: string | null;
}

export interface SubtitleConfigUpdate {
  mindmap_model_id?: number;
  mindmap_prompt?: string;
  is_active?: boolean;
}

// ---------------------------------------------------------------------------
// Batch types
// ---------------------------------------------------------------------------

export interface SubtitleBatchItem {
  share_text: string;
}

export interface SubtitleItem {
  id: number;
  row_number: number;
  original_url: string;
  title: string;
  transcript: string;
  status: 'pending' | 'processing' | 'success' | 'failed';
  error: string;
}

export interface SubtitleJob {
  id: number;
  job_code: string;
  access_code: string;
  status: 'processing' | 'completed' | 'failed';
  phase: string;
  total: number;
  success: number;
  failed: number;
  created_at: string | null;
  updated_at: string | null;
  items?: SubtitleItem[];
}

export interface BatchCreateResponse {
  job_code: string;
  access_code: string;
  total: number;
}

// ---------------------------------------------------------------------------
// Operator API
// ---------------------------------------------------------------------------

/** 单条字幕提取：share_text（抖音链接）或 file_url（已上传 OSS）→ ASR → 字幕 */
export const extractSubtitle = (data: ExtractRequest) =>
  post<ExtractResult>('/api/tools/subtitle/extract', data);

/** 字幕 → AI 思维导图（rootTitle + summary + branches） */
export const generateMindmap = (transcript: string) =>
  post<MindmapResult>('/api/tools/subtitle/mindmap', { transcript });

/** 批量创建字幕任务（多 share_text → 后台执行） */
export const createBatch = (items: SubtitleBatchItem[]) =>
  post<BatchCreateResponse>('/api/tools/subtitle/batch', { items });

/** 按 job_code 查询批量任务（含 items 进度） */
export const getBatchByJobCode = (jobCode: string) =>
  get<SubtitleJob>(`/api/tools/subtitle/batch/${jobCode}`);

/** 按 access_code 跨设备查询批量任务 */
export const getBatchByAccessCode = (accessCode: string) =>
  get<SubtitleJob>(`/api/tools/subtitle/batch/by-access/${accessCode}`);

// ---------------------------------------------------------------------------
// Save to output center
// ---------------------------------------------------------------------------

export interface SaveOutputRequest {
  title: string;
  transcript: string;
  mindmap?: MindmapResult;
}

export interface SavedOutput {
  id: number;
  title: string;
  tool_code: string;
  word_count: number;
  created_at: string | null;
}

/** 保存字幕（+ 可选思维导图）到产出中心，写共享 outputs 表 */
export const saveOutput = (data: SaveOutputRequest) =>
  post<SavedOutput>('/api/tools/subtitle/save-output', data);

// ---------------------------------------------------------------------------
// Admin API
// ---------------------------------------------------------------------------

/** 获取字幕库配置（思维导图 Prompt + 模型） */
export const getSubtitleConfigs = () =>
  get<SubtitleConfig[]>('/api/admin/subtitle/configs');

/** 更新字幕库配置 */
export const updateSubtitleConfig = (data: SubtitleConfigUpdate) =>
  put<SubtitleConfig>('/api/admin/subtitle/configs', data);
