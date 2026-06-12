/**
 * Unit tests for src/api/tiktokWriter.ts
 * Mock fetch/request，不发真实请求。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as requestModule from '../../../api/request';

vi.mock('../../../api/request', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

describe('tiktokWriter API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getPersonas', () => {
    it('calls GET /api/tools/tiktok-writer/kols/personas', async () => {
      const { getPersonas } = await import('../../../api/tiktokWriter');
      vi.mocked(requestModule.get).mockResolvedValue({ personas: [] });
      await getPersonas();
      expect(requestModule.get).toHaveBeenCalledWith('/api/tools/tiktok-writer/kols/personas');
    });
  });

  describe('chatStream', () => {
    it('calls POST /api/tools/tiktok-writer/chat with correct headers', async () => {
      const { chatStream } = await import('../../../api/tiktokWriter');
      mockFetch.mockResolvedValue(new Response('ok'));
      await chatStream({ messages: [], systemPrompt: 'test' });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-writer/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-token',
          }),
        }),
      );
    });

    it('includes createJob and jobContext when provided', async () => {
      const { chatStream } = await import('../../../api/tiktokWriter');
      mockFetch.mockResolvedValue(new Response('ok'));
      await chatStream({
        messages: [],
        systemPrompt: 'test',
        createJob: true,
        jobContext: { tiktokUrl: 'https://t.co/x', likesCount: '200000', selectedPersonaName: 'Alice' },
      });
      const body = JSON.parse(vi.mocked(mockFetch).mock.calls[0][1]!.body as string);
      expect(body.createJob).toBe(true);
      expect(body.jobContext.selectedPersonaName).toBe('Alice');
    });
  });

  describe('exportWord', () => {
    it('calls POST /api/tools/tiktok-writer/export-word with correct headers', async () => {
      const { exportWord } = await import('../../../api/tiktokWriter');
      const mockBlob = new Blob(['fake docx']);
      mockFetch.mockResolvedValue(new Response(mockBlob, { status: 200 }));
      await exportWord({ personaName: 'Alice', topic: 't', content: 'hello' });
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/tools/tiktok-writer/export-word'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });
});
