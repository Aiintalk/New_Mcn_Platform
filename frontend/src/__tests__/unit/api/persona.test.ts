import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet, mockPost, mockDel } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDel: vi.fn(),
}));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  post: mockPost,
  del: mockDel,
}));

import {
  fetchDouyin,
  generatePersona,
  getPersonaKols,
  getPersonaKolIntake,
  getPersonaReports,
  getPersonaReportDetail,
  syncPersonaReportDecisions,
  deletePersonaReport,
} from '../../../api/persona';

describe('persona API — request.ts 封装接口', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetchDouyin calls POST /api/persona/fetch-douyin', async () => {
    const mockResult = {
      nickname: '测试达人',
      sec_user_id: 'SEC123',
      total_videos: 100,
      top10_count: 10,
      recent30_count: 20,
      top10_text: 'TOP10 文本',
      recent30_text: '最近30天文本',
    };
    mockPost.mockResolvedValue(mockResult);

    const result = await fetchDouyin('testuser123');
    expect(mockPost).toHaveBeenCalledWith('/api/persona/fetch-douyin', { url: 'testuser123' });
    expect(result.nickname).toBe('测试达人');
    expect(result.sec_user_id).toBe('SEC123');
    expect(result.total_videos).toBe(100);
  });

  it('getPersonaKols calls the formal KOL list with search and pagination', async () => {
    mockGet.mockResolvedValue({ items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } });

    await getPersonaKols({ page: 1, page_size: 20, keyword: '兔兔' });

    expect(mockGet).toHaveBeenCalledWith('/api/persona/kols', {
      page: 1,
      page_size: 20,
      keyword: '兔兔',
    });
  });

  it('getPersonaKolIntake calls the selected formal KOL intake endpoint', async () => {
    mockGet.mockResolvedValue(null);

    await getPersonaKolIntake(43);

    expect(mockGet).toHaveBeenCalledWith('/api/persona/kols/43/intake');
  });

  it('syncPersonaReportDecisions posts field-level decisions', async () => {
    mockPost.mockResolvedValue({ persona: 'kept', content_plan: 'overwritten' });

    await syncPersonaReportDecisions(88, {
      persona: 'keep',
      content_plan: 'overwrite',
    });

    expect(mockPost).toHaveBeenCalledWith('/api/persona/reports/88/sync-decisions', {
      decisions: {
        persona: 'keep',
        content_plan: 'overwrite',
      },
    });
  });

  it('generatePersona sends the formal kol_id in the streaming request body', async () => {
    const reader = { read: vi.fn() } as unknown as ReadableStreamDefaultReader<Uint8Array>;
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'X-Report-Id': '88' }),
      body: { getReader: () => reader },
    });
    vi.stubGlobal('fetch', mockFetch);

    const result = await generatePersona({ kol_id: 43, influencer_info: '达人资料' });

    expect(result).toEqual({ reader, reportId: 88 });
    expect(mockFetch).toHaveBeenCalledOnce();
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      kol_id: 43,
      influencer_info: '达人资料',
    });
  });

  it('getPersonaReports calls GET /api/persona/reports', async () => {
    const mockReports = [
      { id: 1, influencer_name: '达人1', status: 'ready', created_at: '2026-06-10' },
      { id: 2, influencer_name: '达人2', status: 'generating', created_at: '2026-06-11' },
    ];
    mockGet.mockResolvedValue(mockReports);

    const result = await getPersonaReports();
    expect(mockGet).toHaveBeenCalledWith('/api/persona/reports');
    expect(result).toHaveLength(2);
    expect(result[0].influencer_name).toBe('达人1');
  });

  it('getPersonaReportDetail calls GET /api/persona/reports/:id', async () => {
    const mockDetail = {
      id: 1,
      influencer_name: '达人1',
      status: 'ready',
      profile_result: '人格档案内容',
      plan_result: '内容规划内容',
    };
    mockGet.mockResolvedValue(mockDetail);

    const result = await getPersonaReportDetail(1);
    expect(mockGet).toHaveBeenCalledWith('/api/persona/reports/1');
    expect(result.profile_result).toBe('人格档案内容');
  });

  it('deletePersonaReport calls DELETE /api/persona/reports/:id', async () => {
    mockDel.mockResolvedValue({ deleted: true });

    const result = await deletePersonaReport(1);
    expect(mockDel).toHaveBeenCalledWith('/api/persona/reports/1');
    expect(result.deleted).toBe(true);
  });
});

describe('persona API — fetchDouyin 参数传递', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('传递抖音号', async () => {
    mockPost.mockResolvedValue({
      nickname: '达人', sec_user_id: 'SEC', total_videos: 0,
      top10_count: 0, recent30_count: 0, top10_text: '', recent30_text: '',
    });
    await fetchDouyin('DNX833');
    expect(mockPost).toHaveBeenCalledWith('/api/persona/fetch-douyin', { url: 'DNX833' });
  });

  it('传递链接', async () => {
    mockPost.mockResolvedValue({
      nickname: '达人', sec_user_id: 'SEC', total_videos: 0,
      top10_count: 0, recent30_count: 0, top10_text: '', recent30_text: '',
    });
    await fetchDouyin('https://www.douyin.com/user/SEC123');
    expect(mockPost).toHaveBeenCalledWith('/api/persona/fetch-douyin', { url: 'https://www.douyin.com/user/SEC123' });
  });

  it('传递分享短链接', async () => {
    mockPost.mockResolvedValue({
      nickname: '达人', sec_user_id: 'SEC', total_videos: 0,
      top10_count: 0, recent30_count: 0, top10_text: '', recent30_text: '',
    });
    await fetchDouyin('https://v.douyin.com/abc123/');
    expect(mockPost).toHaveBeenCalledWith('/api/persona/fetch-douyin', { url: 'https://v.douyin.com/abc123/' });
  });
});

describe('persona API — 错误处理', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetchDouyin 网络错误应抛出', async () => {
    mockPost.mockRejectedValue(new Error('网络错误'));
    await expect(fetchDouyin('test')).rejects.toThrow('网络错误');
  });

  it('getPersonaReportDetail 404 应抛出', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('报告不存在'), { code: 'RESOURCE_NOT_FOUND' }));
    await expect(getPersonaReportDetail(99999)).rejects.toThrow('报告不存在');
  });

  it('deletePersonaReport 404 应抛出', async () => {
    mockDel.mockRejectedValue(Object.assign(new Error('报告不存在'), { code: 'RESOURCE_NOT_FOUND' }));
    await expect(deletePersonaReport(99999)).rejects.toThrow('报告不存在');
  });
});
