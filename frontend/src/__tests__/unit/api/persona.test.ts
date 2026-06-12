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
  getKolSubmissions,
  getPersonaReports,
  getPersonaReportDetail,
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

  it('getKolSubmissions calls GET /api/persona/kol-submissions', async () => {
    mockGet.mockResolvedValue([]);
    await getKolSubmissions();
    expect(mockGet).toHaveBeenCalledWith('/api/persona/kol-submissions');
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
