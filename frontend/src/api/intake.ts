import { get, post, patch, del, put } from './request';
import type {
  ChatMessage, IntakeQuestion, IntakeLink,
  IntakeSubmission, IntakeConfigForm, QuestionForm,
} from '../types/intake';

const BASE_URL_INTAKE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ── Public API (no auth header needed) ────────────────────────────────────────

export const getIntakeQuestions = () =>
  get<IntakeQuestion[]>('/api/intake/questions');

export const bridgeIntake = (token: string, data: {
  user_answer: string;
  question_text: string;
  next_question_text?: string;
  next_question_hint?: string;
  is_last_question?: boolean;
  is_section_change?: boolean;
  next_section?: string;
  is_multi_collect?: boolean;
  collect_count?: number;
}) => post<{ reply: string }>(`/api/intake/${token}/bridge`, data);

export const getIntakeInfo = (token: string) =>
  get<{ valid: boolean; kol_name: string | null; already_submitted: boolean; existing_messages: ChatMessage[] }>(
    `/api/intake/${token}`,
  );

export const chatIntake = (token: string, messages: ChatMessage[]) =>
  post<{ reply: string }>(`/api/intake/${token}/chat`, { messages });

export const submitIntake = (token: string, messages: ChatMessage[]) =>
  post<{ report_status: string }>(`/api/intake/${token}/submit`, { messages });

export const getIntakeStatus = (token: string) =>
  get<{ report_status: 'pending' | 'generating' | 'ready' | 'failed' }>(
    `/api/intake/${token}/status`,
  );

export const getIntakeDownloadUrl = (token: string, format: 'docx' | 'pdf') =>
  `${BASE_URL_INTAKE}/api/intake/${token}/download?format=${format}`;

// ── Operator API ───────────────────────────────────────────────────────────────

export const createIntakeLink = (data: { kol_name?: string; expire_hours: number }) =>
  post<{ id: number; token: string; expires_at: string }>('/api/operator/intake/links', data);

export const getIntakeLinks = () =>
  get<IntakeLink[]>('/api/operator/intake/links');

export const getOperatorSubmissions = () =>
  get<IntakeSubmission[]>('/api/operator/intake/submissions');

export const getOperatorSubmissionDetail = (id: number) =>
  get<IntakeSubmission>(`/api/operator/intake/submissions/${id}`);

export const getOperatorDownloadUrl = (id: number, format: 'docx' | 'pdf') =>
  `${BASE_URL_INTAKE}/api/operator/intake/submissions/${id}/download?format=${format}`;

// ── Admin API ──────────────────────────────────────────────────────────────────

export const getAdminQuestions = () =>
  get<IntakeQuestion[]>('/api/admin/intake/questions');

export const createQuestion = (data: QuestionForm) =>
  post<{ id: number }>('/api/admin/intake/questions', data);

export const updateQuestion = (id: number, data: Partial<QuestionForm> & { is_active?: boolean }) =>
  patch<IntakeQuestion>(`/api/admin/intake/questions/${id}`, data);

export const deleteQuestion = (id: number) =>
  del<null>(`/api/admin/intake/questions/${id}`);

export const reorderQuestions = (items: { id: number; order_num: number }[]) =>
  put<null>('/api/admin/intake/questions/reorder', items);

export const getIntakeConfigs = () =>
  get<{ id: number; config_key: string; ai_model_id: number | null; system_prompt: string | null; is_active: boolean }[]>(
    '/api/admin/intake/configs',
  );

export const updateIntakeConfig = (key: string, data: IntakeConfigForm) =>
  put<null>(`/api/admin/intake/configs/${key}`, data);

export const getAdminSubmissions = () =>
  get<IntakeSubmission[]>('/api/admin/intake/submissions');

export const getAdminSubmissionDetail = (id: number) =>
  get<IntakeSubmission>(`/api/admin/intake/submissions/${id}`);

export const regenerateReport = (id: number) =>
  post<null>(`/api/admin/intake/submissions/${id}/regenerate`, {});
