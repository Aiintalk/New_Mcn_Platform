import { get, put, post } from './request';
import type { ScriptReviewConfig, ReviewRequest, ReviewResult } from '../types/scriptReview';

export const getConfig = () =>
  get<ScriptReviewConfig>('/api/admin/qianchuan-script-review/config');

export const updateConfig = (body: Partial<ScriptReviewConfig>) =>
  put('/api/admin/qianchuan-script-review/config', body);

export const submitReview = (body: ReviewRequest) =>
  post<ReviewResult>('/api/operator/qianchuan-script-review/review', body);
