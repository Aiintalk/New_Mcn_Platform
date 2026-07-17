/**
 * Unit tests for personaWriter.ts API error extraction.
 *
 * Covers PR #18 Bug #14 fix: 3 stream functions (evaluateOpeningStream /
 * analyzeStructureStream / chatStream) changed error extraction from
 * `err?.detail?.message` → `err?.message`. Tests lock this behavior to
 * prevent regression.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock authStore before importing personaWriter
let mockToken: string | null = 'test-jwt';

vi.mock('../../../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ token: mockToken }),
  },
}));

import {
  evaluateOpeningStream,
  analyzeStructureStream,
  chatStream,
} from '../../../api/personaWriter';

function buildErrorResponse(status: number, body: unknown) {
  return {
    ok: false,
    status,
    body: null,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

describe('personaWriter stream error extraction (PR #18 Bug #14)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockToken = 'test-jwt';
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('evaluateOpeningStream throws err.message (not err.detail.message)', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        buildErrorResponse(500, { message: '上游 AI 服务不可用' }) as Response,
      );

    await expect(evaluateOpeningStream('transcript', () => {})).rejects.toThrow(
      '上游 AI 服务不可用',
    );
    expect(fetchSpy).toHaveBeenCalled();
  });

  it('analyzeStructureStream throws err.message (not err.detail.message)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      buildErrorResponse(500, { message: '结构拆解失败' }) as Response,
    );

    await expect(analyzeStructureStream('transcript', () => {})).rejects.toThrow(
      '结构拆解失败',
    );
  });

  it('chatStream throws err.message (not err.detail.message)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      buildErrorResponse(500, { message: '内容生成失败' }) as Response,
    );

    await expect(
      chatStream({ scene: 'writing', persona_id: 1, transcript: 't', structure_analysis: 's', messages: [] }, () => {}),
    ).rejects.toThrow('内容生成失败');
  });

  it('evaluateOpeningStream falls back to status-code message when body has no message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      buildErrorResponse(503, {}) as Response,
    );

    await expect(evaluateOpeningStream('t', () => {})).rejects.toThrow(
      /评估失败: 503/,
    );
  });

  it('analyzeStructureStream falls back to status-code message when body has no message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      buildErrorResponse(429, {}) as Response,
    );

    await expect(analyzeStructureStream('t', () => {})).rejects.toThrow(
      /拆解失败: 429/,
    );
  });

  it('chatStream falls back to status-code message when body has no message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      buildErrorResponse(500, {}) as Response,
    );

    await expect(
      chatStream({ scene: 'writing', persona_id: 1, transcript: 't', structure_analysis: 's', messages: [] }, () => {}),
    ).rejects.toThrow(/生成失败: 500/);
  });
});
