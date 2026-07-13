import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../api/request', () => ({ post: vi.fn() }));
vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'test-token' }) },
}));

const mockFetch = vi.fn();
global.fetch = mockFetch as unknown as typeof fetch;

describe('filmReview API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends kol_id with both complete video files to the platform backend', async () => {
    const { analyzeFilm } = await import('../../../api/filmReview');
    const original = new File(['original'], 'original.mp4', { type: 'video/mp4' });
    const edited = new File(['edited'], 'edited.mov', { type: 'video/quicktime' });
    mockFetch.mockResolvedValue(new Response('stream', { status: 200 }));

    await analyzeFilm(7, original, edited);

    const [, options] = mockFetch.mock.calls[0] as [string, RequestInit];
    const body = options.body as FormData;
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/tools/qianchuan-preview/analyze-video'),
      expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer test-token' } }),
    );
    expect(body.get('kol_id')).toBe('7');
    expect((body.get('original') as File).name).toBe('original.mp4');
    expect((body.get('edited') as File).name).toBe('edited.mov');
  });
});
