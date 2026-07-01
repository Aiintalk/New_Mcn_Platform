import { get, put, post } from './request';
import type {
  ScriptReviewConfig,
  ReviewRequest,
  ReviewResult,
  ScriptReviewSaveOutputRequest,
} from '../types/scriptReview';

export const getConfig = () =>
  get<ScriptReviewConfig>('/api/admin/qianchuan-script-review/config');

export const updateConfig = (body: Partial<ScriptReviewConfig>) =>
  put('/api/admin/qianchuan-script-review/config', body);

export const submitReview = (body: ReviewRequest) =>
  post<ReviewResult>('/api/operator/qianchuan-script-review/review', body);

/** 保存脚本预审结果至历史（手动保存） */
export const saveOutput = (body: ScriptReviewSaveOutputRequest) =>
  post<{ output_id: number }>('/api/operator/qianchuan-script-review/save-output', body);
