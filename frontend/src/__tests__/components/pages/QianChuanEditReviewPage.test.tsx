import { App } from 'antd';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockExtractFrames, mockTranscribeVideo, mockChatStream } = vi.hoisted(() => ({
  mockExtractFrames: vi.fn(),
  mockTranscribeVideo: vi.fn(),
  mockChatStream: vi.fn(),
}));

vi.mock('../../../api/qianchuanEditReview', () => ({
  extractFrames: mockExtractFrames,
  transcribeVideo: mockTranscribeVideo,
  chatStream: mockChatStream,
  exportWord: vi.fn(),
  saveOutput: vi.fn(),
  getConfig: vi.fn().mockResolvedValue({ system_prompt: '', ai_model_id: null }),
}));

import QianChuanEditReviewPage from '../../../pages/operator/QianChuanEditReviewPage';

function renderPage() {
  return render(<App><QianChuanEditReviewPage /></App>);
}

const frameResult = { frames: [{ time: 1, base64: 'data:image/jpeg;base64,AA==' }], duration: 10 };

describe('QianChuanEditReviewPage 双侧就绪门禁', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockExtractFrames.mockResolvedValue(frameResult);
    mockTranscribeVideo.mockResolvedValue({ text: '自动转录文案' });
  });

  it('截帧成功但转录失败时保留帧、阻止预审，手动文案可恢复就绪', async () => {
    const user = userEvent.setup();
    mockTranscribeVideo.mockRejectedValueOnce(new Error('转录服务失败'));
    renderPage();

    const analyzeButton = screen.getByRole('button', { name: '开始预审' });
    expect(analyzeButton).toBeDisabled();
    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['video'], 'original.mp4', { type: 'video/mp4' }));
    expect(await screen.findByText('待处理')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));

    expect(await screen.findByText('转录失败，尚未就绪')).toBeInTheDocument();
    expect(screen.getByText('已提取 1 帧截图')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试转录' })).toBeInTheDocument();
    expect(analyzeButton).toBeDisabled();

    await user.type(screen.getAllByPlaceholderText('点击上方按钮自动提取，或直接粘贴文案...')[0], '手动补全文案');
    expect(await screen.findByText('已就绪')).toBeInTheDocument();
    expect(analyzeButton).toBeDisabled();

    await user.clear(screen.getAllByPlaceholderText('点击上方按钮自动提取，或直接粘贴文案...')[0]);
    expect(await screen.findByText('文案为空，尚未就绪')).toBeInTheDocument();
    expect(analyzeButton).toBeDisabled();
  });

  it('截帧失败时显示失败状态和明确的重试截帧入口', async () => {
    const user = userEvent.setup();
    mockExtractFrames.mockRejectedValueOnce(new Error('浏览器截帧失败'));
    renderPage();

    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['video'], 'original.mp4', { type: 'video/mp4' }));
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));

    expect(await screen.findByText('截帧失败，尚未就绪')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试截帧' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
  });

  it('两侧都就绪后才允许预审，空分析结果不展示保存和导出', async () => {
    const user = userEvent.setup();
    mockChatStream.mockResolvedValue(new Response('', { status: 200 }));
    renderPage();

    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['a'], 'original.mp4', { type: 'video/mp4' }));
    await user.upload(screen.getByLabelText('上传我方成片视频'), new File(['b'], 'ours.mp4', { type: 'video/mp4' }));
    const processButtons = screen.getAllByRole('button', { name: '截帧 + 提取文案' });
    await user.click(processButtons[0]);
    await waitFor(() => expect(screen.getAllByText('已就绪')).toHaveLength(1));
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    await waitFor(() => expect(screen.getAllByText('已就绪')).toHaveLength(2));

    const analyzeButton = screen.getByRole('button', { name: '开始预审' });
    expect(analyzeButton).toBeEnabled();
    await user.click(analyzeButton);
    expect(await screen.findByRole('alert')).toHaveTextContent('AI 未返回有效报告，请重新预审');
    expect(screen.queryByRole('button', { name: /导出 Word/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /保存报告/ })).not.toBeInTheDocument();
  });
});
