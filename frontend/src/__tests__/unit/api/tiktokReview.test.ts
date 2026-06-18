/**
 * Unit tests for src/api/tiktokReview.ts
 * Mock fetch/request，不发真实请求。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as requestModule from '../../../api/request';

vi.mock('../../../api/request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

describe('tiktokReview API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('saveReport', () => {
    it('calls POST /api/tools/tiktok-review/save with correct body', async () => {
      const { saveReport } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.post).mockResolvedValue({ output_id: 42 });
      const result = await saveReport({ content: '报告内容', title: 'TT复盘' });
      expect(requestModule.post).toHaveBeenCalledWith(
        '/api/tools/tiktok-review/save',
        { content: '报告内容', title: 'TT复盘' }
      );
      expect(result.output_id).toBe(42);
    });

    it('throws when post fails', async () => {
      const { saveReport } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.post).mockRejectedValue(new Error('保存失败'));
      await expect(saveReport({ content: '内容' })).rejects.toThrow('保存失败');
    });
  });

  describe('getOutputs', () => {
    it('calls GET /api/tools/tiktok-review/outputs with pagination', async () => {
      const { getOutputs } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.get).mockResolvedValue({ items: [], total: 0 });
      await getOutputs(2, 5);
      expect(requestModule.get).toHaveBeenCalledWith(
        '/api/tools/tiktok-review/outputs',
        { page: 2, size: 5 }
      );
    });
  });

  describe('exportWord', () => {
    it('calls POST /api/tools/tiktok-review/export-word with correct headers', async () => {
      const { exportWord } = await import('../../../api/tiktokReview');
      const mockBlob = new Blob(['fake docx']);
      mockFetch.mockResolvedValue(new Response(mockBlob, { status: 200 }));
      await exportWord('报告内容', 'TT复盘报告');
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-review/export-word'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        })
      );
    });

    it('throws when export fails', async () => {
      const { exportWord } = await import('../../../api/tiktokReview');
      mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ detail: { message: '导出失败' } }), { status: 500 })
      );
      await expect(exportWord('内容')).rejects.toThrow('导出失败');
    });
  });

  describe('getAdminConfigs', () => {
    it('calls GET /api/admin/tiktok-review/configs', async () => {
      const { getAdminConfigs } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.get).mockResolvedValue([]);
      await getAdminConfigs();
      expect(requestModule.get).toHaveBeenCalledWith('/api/admin/tiktok-review/configs');
    });
  });

  describe('updateAdminConfig', () => {
    it('calls PUT /api/admin/tiktok-review/configs/:key', async () => {
      const { updateAdminConfig } = await import('../../../api/tiktokReview');
      vi.mocked(requestModule.put).mockResolvedValue({ config_key: 'default' });
      await updateAdminConfig('default', {
        ai_model_id: null,
        system_prompt: 'New prompt',
        is_active: true,
      });
      expect(requestModule.put).toHaveBeenCalledWith(
        '/api/admin/tiktok-review/configs/default',
        { ai_model_id: null, system_prompt: 'New prompt', is_active: true }
      );
    });
  });

  describe('generateStream', () => {
    it('calls POST /api/tools/tiktok-review/generate with auth header', async () => {
      const { generateStream } = await import('../../../api/tiktokReview');
      mockFetch.mockResolvedValue(new Response('stream', { status: 200 }));
      await generateStream({
        original_transcript: '原版',
        original_likes: '1万',
        copycat_transcript: '仿写',
        copycat_likes: '500',
      });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-review/generate'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({ Authorization: 'Bearer test-token' }),
        })
      );
    });
  });
});
