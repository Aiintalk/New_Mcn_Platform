import { get, post } from './request';
import { useAuthStore } from '../store/authStore';
import type { ChatMessage } from '../types/intake';

export interface DirectSession {
  id: number;
  kol_name: string | null;
  report_status: 'pending' | 'generating' | 'ready' | 'failed';
  ai_report: string | null;
  report_generated_at: string | null;
  created_at: string | null;
}

export const getDirectSessions = () =>
  get<DirectSession[]>('/api/operator/intake/direct/sessions');

export const startDirectSession = (data: { kol_name?: string }) =>
  post<{ session_id: number; kol_name: string | null }>(
    '/api/operator/intake/direct/start', data
  );

export const chatDirect = (sessionId: number, messages: ChatMessage[]) =>
  post<{ reply: string }>(
    `/api/operator/intake/direct/${sessionId}/chat`, { messages }
  );

export const submitDirect = (sessionId: number, messages: ChatMessage[]) =>
  post<{ report_status: string }>(
    `/api/operator/intake/direct/${sessionId}/submit`,
    { messages }
  );

export const getDirectStatus = (sessionId: number) =>
  get<{
    report_status: 'pending' | 'generating' | 'ready' | 'failed';
    ai_report: string | null;
  }>(`/api/operator/intake/direct/${sessionId}/status`);

export const bridgeOperatorDirect = (sessionId: number, data: {
  user_answer: string;
  question_text: string;
  next_question_text?: string;
  is_last_question?: boolean;
  is_section_change?: boolean;
  next_section?: string;
  is_multi_collect?: boolean;
  collect_count?: number;
}) => post<{ reply: string }>(`/api/operator/intake/direct/${sessionId}/bridge`, data);

export const getDirectDownloadUrl = (sessionId: number, format: 'docx' | 'pdf') => {
  const base = import.meta.env.VITE_API_BASE_URL ?? '';
  const token = useAuthStore.getState().token;
  const tokenParam = token ? `&token=${encodeURIComponent(token)}` : '';
  return `${base}/api/operator/intake/direct/${sessionId}/download?format=${format}${tokenParam}`;
};
