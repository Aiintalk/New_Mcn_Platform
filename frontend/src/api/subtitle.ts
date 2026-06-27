import { get, post, put, del } from './request';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** POST /extract 响应（异步任务化后只返回 job_code） */
export interface ExtractResponse {
  job_code: string;
  status: 'processing';
}

export interface ExtractRequest {
  share_text?: string;
  file_url?: string;
}

/** 单条任务完成后从 item 里扁平出来的视频元信息 */
export interface VideoMeta {
  play_url?: string;
  audio_url?: string;
  cover_url?: string | null;
  nickname?: string;
  digg_count?: number;
  aweme_id?: string;
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

export interface SubtitleItem extends VideoMeta {
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
  /** single（单条 extract）| batch（批量任务） */
  kind: 'single' | 'batch';
  status: 'processing' | 'completed' | 'failed';
  phase: string;
  total: number;
  success: number;
  failed: number;
  created_by: number | null;
  created_by_username?: string;
  created_at: string | null;
  updated_at: string | null;
  items?: SubtitleItem[];
}

export interface BatchCreateResponse {
  job_code: string;
  total: number;
}

export interface PaginationData {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface BatchListResponse {
  items: SubtitleJob[];
  pagination: PaginationData;
}

// ---------------------------------------------------------------------------
// Operator API
// ---------------------------------------------------------------------------

/** 单条字幕提取（异步）：share_text/file_url → 创建 job → 返回 job_code → 前端轮询 */
export const extractSubtitle = (data: ExtractRequest) =>
  post<ExtractResponse>('/api/tools/subtitle/extract', data);

/** 字幕 → AI 思维导图（rootTitle + summary + branches） */
export const generateMindmap = (transcript: string) =>
  post<MindmapResult>('/api/tools/subtitle/mindmap', { transcript });

/** 批量创建字幕任务（多 share_text → 后台执行） */
export const createBatch = (items: SubtitleBatchItem[]) =>
  post<BatchCreateResponse>('/api/tools/subtitle/batch', { items });

/** 按 job_code 查询任务详情（含 items / transcript / 视频元信息） */
export const getBatchByJobCode = (jobCode: string) =>
  get<SubtitleJob>(`/api/tools/subtitle/batch/${jobCode}`);

/** 历史记录列表（单条 + 批量统一展示，按 created_at 倒序，过滤软删除） */
export const listHistory = (page = 1, pageSize = 20) =>
  get<BatchListResponse>('/api/tools/subtitle/batches', {
    page,
    page_size: pageSize,
  });

/** 兼容旧调用方（已改为 listHistory，行为一致） */
export const listMyBatches = listHistory;

/** 软删除一条历史记录（设置 deleted_at） */
export const deleteHistory = (jobCode: string) =>
  del<{ job_code: string; deleted: boolean }>(`/api/tools/subtitle/batch/${jobCode}`);

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
