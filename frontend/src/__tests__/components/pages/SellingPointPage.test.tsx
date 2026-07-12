/**
 * SellingPointPage unit tests for PR #18 [ERROR] handling.
 *
 * PR #18 added: when AI stream ends with `[ERROR]` marker (from backend
 * `_RETRY_DELAYS` exhausting), the page strips the marker from result and
 * shows a friendly error banner instead of polluting the analysis report.
 *
 * Coverage:
 * - Stream end with [ERROR] → result cleaned + friendly error shown
 * - Stream end without [ERROR] → result kept, no error
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// ── Mock API ──────────────────────────────────────────────────────────
const mockChatStream = vi.fn();
const mockParseFile = vi.fn();
const mockSaveHistory = vi.fn();
const mockGetHistoryList = vi.fn();
const mockGetHistoryRecord = vi.fn();
const mockDeleteHistoryRecord = vi.fn();

vi.mock('../../../api/sellingPoint', () => ({
  chatStream: (...args: unknown[]) => mockChatStream(...args),
  parseFile: (...args: unknown[]) => mockParseFile(...args),
  saveHistory: (...args: unknown[]) => mockSaveHistory(...args),
  getHistoryList: (...args: unknown[]) => mockGetHistoryList(...args),
  getHistoryRecord: (...args: unknown[]) => mockGetHistoryRecord(...args),
  deleteHistoryRecord: (...args: unknown[]) => mockDeleteHistoryRecord(...args),
}));

import SellingPointPage from '../../../pages/operator/SellingPointPage';

// ── Helpers: build a fake streaming Response ─────────────────────────
function makeFakeResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const reader = {
    read: async () => {
      if (i < chunks.length) {
        const value = encoder.encode(chunks[i++]);
        return { done: false, value };
      }
      return { done: true, value: undefined };
    },
  };
  return { body: { getReader: () => reader } } as unknown as Response;
}

describe('SellingPointPage [ERROR] handling (PR #18)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockGetHistoryList.mockResolvedValue({ records: [] });
    mockSaveHistory.mockResolvedValue({});
    mockParseFile.mockResolvedValue({ filename: 't.txt', text: 'parsed' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /**
   * Drive the page to step 2 (script upload) by entering brief content,
   * then input script content and click "开始提取卖点".
   */
  async function driveToAnalyze(user: ReturnType<typeof userEvent.setup>) {
    // Step 1: paste brief content → click "下一步"
    const briefTextarea = await screen.findByPlaceholderText('粘贴产品Brief内容...');
    await user.type(briefTextarea, '我的产品 Brief 内容');
    await user.click(screen.getByText('下一步：上传达人文案 →'));

    // Step 2: paste script content → click "开始提取卖点"
    const scriptTextarea = await screen.findByPlaceholderText('粘贴达人文案脚本...');
    await user.type(scriptTextarea, '达人脚本内容');
    await user.click(screen.getByText('开始提取卖点'));
  }

  it('shows friendly error when stream ends with [ERROR] marker', async () => {
    const user = userEvent.setup();
    mockChatStream.mockResolvedValue(
      makeFakeResponse(['【机制】特殊成分', '\n\n[ERROR] 503 Service Unavailable']),
    );

    render(<SellingPointPage />);

    await driveToAnalyze(user);

    // PR #18 contract: friendly error banner, includes upstream reason
    await waitFor(() => {
      expect(
        screen.getByText(/AI 服务暂时不可用.*503 Service Unavailable/),
      ).toBeInTheDocument();
    });

    // Result is cleaned: marker removed, real content kept
    const resultArea = screen.getByText(/特殊成分/);
    expect(resultArea).toBeInTheDocument();
    expect(screen.queryByText(/\[ERROR\]/)).not.toBeInTheDocument();
  });

  it('keeps full result and shows no error when stream is healthy', async () => {
    const user = userEvent.setup();
    mockChatStream.mockResolvedValue(
      makeFakeResponse(['【机制】机制内容', '\n【背书】背书内容']),
    );

    render(<SellingPointPage />);

    await driveToAnalyze(user);

    await waitFor(() => {
      expect(screen.getByText(/机制内容/)).toBeInTheDocument();
    });
    expect(screen.getByText(/背书内容/)).toBeInTheDocument();
    expect(screen.queryByText(/AI 服务暂时不可用/)).not.toBeInTheDocument();
  });
});
