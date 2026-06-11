import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet, mockPost, mockPatch, mockDel, mockPut } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDel: vi.fn(),
  mockPut: vi.fn(),
}));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  post: mockPost,
  patch: mockPatch,
  del: mockDel,
  put: mockPut,
}));

import {
  getIntakeQuestions,
  getIntakeInfo,
  chatIntake,
  submitIntake,
  getIntakeStatus,
  createIntakeLink,
  getIntakeLinks,
  getOperatorSubmissions,
  getOperatorSubmissionDetail,
  getAdminQuestions,
  createQuestion,
  updateQuestion,
  deleteQuestion,
  getIntakeConfigs,
  updateIntakeConfig,
  getAdminSubmissions,
  regenerateReport,
} from '../../../api/intake';

describe('intake API — public endpoints', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getIntakeQuestions calls GET /api/intake/questions', async () => {
    mockGet.mockResolvedValue([]);
    await getIntakeQuestions();
    expect(mockGet).toHaveBeenCalledWith('/api/intake/questions');
  });

  it('getIntakeInfo calls GET /api/intake/:token', async () => {
    const info = { valid: true, kol_name: 'Test', already_submitted: false, existing_messages: [] };
    mockGet.mockResolvedValue(info);
    const result = await getIntakeInfo('abc123');
    expect(mockGet).toHaveBeenCalledWith('/api/intake/abc123');
    expect(result.valid).toBe(true);
  });

  it('chatIntake calls POST /api/intake/:token/chat', async () => {
    mockPost.mockResolvedValue({ reply: 'Hello!' });
    const result = await chatIntake('abc123', []);
    expect(mockPost).toHaveBeenCalledWith('/api/intake/abc123/chat', { messages: [] });
    expect(result.reply).toBe('Hello!');
  });

  it('submitIntake calls POST /api/intake/:token/submit', async () => {
    mockPost.mockResolvedValue({ report_status: 'generating' });
    const result = await submitIntake('abc123', [{ role: 'user', content: 'Hi' }]);
    expect(mockPost).toHaveBeenCalledWith('/api/intake/abc123/submit', {
      messages: [{ role: 'user', content: 'Hi' }],
    });
    expect(result.report_status).toBe('generating');
  });

  it('getIntakeStatus calls GET /api/intake/:token/status', async () => {
    mockGet.mockResolvedValue({ report_status: 'ready' });
    const result = await getIntakeStatus('abc123');
    expect(mockGet).toHaveBeenCalledWith('/api/intake/abc123/status');
    expect(result.report_status).toBe('ready');
  });
});

describe('intake API — operator endpoints', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('createIntakeLink calls POST /api/operator/intake/links', async () => {
    mockPost.mockResolvedValue({ id: 1, token: 'xyz', expires_at: '2026-06-10T00:00:00Z' });
    const result = await createIntakeLink({ kol_name: 'Test', expire_hours: 24 });
    expect(mockPost).toHaveBeenCalledWith('/api/operator/intake/links', { kol_name: 'Test', expire_hours: 24 });
    expect(result.token).toBe('xyz');
  });

  it('getIntakeLinks calls GET /api/operator/intake/links', async () => {
    mockGet.mockResolvedValue([]);
    await getIntakeLinks();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/intake/links');
  });

  it('getOperatorSubmissions calls GET /api/operator/intake/submissions', async () => {
    mockGet.mockResolvedValue([]);
    await getOperatorSubmissions();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/intake/submissions');
  });

  it('getOperatorSubmissionDetail calls GET /api/operator/intake/submissions/:id', async () => {
    mockGet.mockResolvedValue({ id: 1, messages: [], ai_report: 'Report' });
    const result = await getOperatorSubmissionDetail(1);
    expect(mockGet).toHaveBeenCalledWith('/api/operator/intake/submissions/1');
    expect(result.ai_report).toBe('Report');
  });
});

describe('intake API — admin endpoints', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getAdminQuestions calls GET /api/admin/intake/questions', async () => {
    mockGet.mockResolvedValue([]);
    await getAdminQuestions();
    expect(mockGet).toHaveBeenCalledWith('/api/admin/intake/questions');
  });

  it('createQuestion calls POST /api/admin/intake/questions', async () => {
    mockPost.mockResolvedValue({ id: 1 });
    const result = await createQuestion({ order_num: 1, category: 'test', question_text: 'Q?' });
    expect(mockPost).toHaveBeenCalledWith('/api/admin/intake/questions', { order_num: 1, category: 'test', question_text: 'Q?' });
    expect(result.id).toBe(1);
  });

  it('updateQuestion calls PATCH /api/admin/intake/questions/:id', async () => {
    mockPatch.mockResolvedValue({ id: 1 });
    await updateQuestion(1, { question_text: 'Updated?' });
    expect(mockPatch).toHaveBeenCalledWith('/api/admin/intake/questions/1', { question_text: 'Updated?' });
  });

  it('deleteQuestion calls DELETE /api/admin/intake/questions/:id', async () => {
    mockDel.mockResolvedValue(null);
    await deleteQuestion(1);
    expect(mockDel).toHaveBeenCalledWith('/api/admin/intake/questions/1');
  });

  it('getIntakeConfigs calls GET /api/admin/intake/configs', async () => {
    mockGet.mockResolvedValue([]);
    await getIntakeConfigs();
    expect(mockGet).toHaveBeenCalledWith('/api/admin/intake/configs');
  });

  it('updateIntakeConfig calls PUT /api/admin/intake/configs/:key', async () => {
    mockPut.mockResolvedValue(null);
    await updateIntakeConfig('conversation_bridge', { ai_model_id: 1, system_prompt: 'Hello' });
    expect(mockPut).toHaveBeenCalledWith('/api/admin/intake/configs/conversation_bridge', { ai_model_id: 1, system_prompt: 'Hello' });
  });

  it('getAdminSubmissions calls GET /api/admin/intake/submissions', async () => {
    mockGet.mockResolvedValue([]);
    await getAdminSubmissions();
    expect(mockGet).toHaveBeenCalledWith('/api/admin/intake/submissions');
  });

  it('regenerateReport calls POST /api/admin/intake/submissions/:id/regenerate', async () => {
    mockPost.mockResolvedValue(null);
    await regenerateReport(1);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/intake/submissions/1/regenerate', {});
  });
});
