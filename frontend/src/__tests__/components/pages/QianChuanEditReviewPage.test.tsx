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

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('QianChuanEditReviewPage 双侧就绪门禁', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
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

  it('已就绪侧重新处理或重试转录期间不再被旧文案误判为就绪', async () => {
    const user = userEvent.setup();
    let resolveTranscription: ((value: { text: string }) => void) | undefined;
    renderPage();

    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['a'], 'original.mp4', { type: 'video/mp4' }));
    await user.upload(screen.getByLabelText('上传我方成片视频'), new File(['b'], 'ours.mp4', { type: 'video/mp4' }));
    await user.click(screen.getAllByRole('button', { name: '截帧 + 提取文案' })[0]);
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    await waitFor(() => expect(screen.getAllByText('已就绪')).toHaveLength(2));
    expect(screen.getByRole('button', { name: '开始预审' })).toBeEnabled();

    mockTranscribeVideo.mockImplementationOnce(() => new Promise(resolve => { resolveTranscription = resolve; }));
    await user.click(screen.getAllByRole('button', { name: '重新处理' })[0]);

    expect(await screen.findByText('转录中')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
    resolveTranscription?.({ text: '重新转录完成' });
    await waitFor(() => expect(screen.getAllByText('已就绪')).toHaveLength(2));
  });

  it('报告成功后任一输入变化会立即关闭旧报告的保存和导出', async () => {
    const user = userEvent.setup();
    mockChatStream.mockResolvedValue(new Response('# 有效报告', { status: 200 }));
    renderPage();

    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['a'], 'original.mp4', { type: 'video/mp4' }));
    await user.upload(screen.getByLabelText('上传我方成片视频'), new File(['b'], 'ours.mp4', { type: 'video/mp4' }));
    await user.click(screen.getAllByRole('button', { name: '截帧 + 提取文案' })[0]);
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    await waitFor(() => expect(screen.getAllByText('已就绪')).toHaveLength(2));
    await user.click(screen.getByRole('button', { name: '开始预审' }));

    expect(await screen.findByText('保存报告', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText('导出 Word')).toBeInTheDocument();
    await user.type(screen.getAllByPlaceholderText('点击上方按钮自动提取，或直接粘贴文案...')[0], '新内容');
    expect(screen.queryByText('保存报告')).not.toBeInTheDocument();
    expect(screen.queryByText('导出 Word')).not.toBeInTheDocument();
  });

  it('视频 A 截帧中替换为 B 后忽略 A 的迟到响应', async () => {
    const user = userEvent.setup();
    const oldExtraction = deferred<typeof frameResult>();
    mockExtractFrames.mockReturnValueOnce(oldExtraction.promise);
    renderPage();

    const upload = screen.getByLabelText('上传原版爆款视频');
    await user.upload(upload, new File(['a'], 'video-a.mp4', { type: 'video/mp4' }));
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    expect(await screen.findByText('截帧中')).toBeInTheDocument();

    await user.upload(upload, new File(['b'], 'video-b.mp4', { type: 'video/mp4' }));
    oldExtraction.resolve(frameResult);

    await waitFor(() => expect(screen.getByText('video-b.mp4')).toBeInTheDocument());
    expect(screen.getByText('待处理')).toBeInTheDocument();
    expect(screen.queryByText('已提取 1 帧截图')).not.toBeInTheDocument();
    expect(mockTranscribeVideo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
  });

  it('视频 A 截帧中删除文件后忽略 A 的迟到响应', async () => {
    const user = userEvent.setup();
    const oldExtraction = deferred<typeof frameResult>();
    mockExtractFrames.mockReturnValueOnce(oldExtraction.promise);
    renderPage();

    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['a'], 'video-a.mp4', { type: 'video/mp4' }));
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    expect(await screen.findByText('截帧中')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '✕' }));
    oldExtraction.resolve(frameResult);

    await waitFor(() => expect(screen.getAllByText('未上传')).toHaveLength(2));
    expect(screen.queryByText('已提取 1 帧截图')).not.toBeInTheDocument();
    expect(mockTranscribeVideo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
  });

  it('截帧中人工输入文案后忽略旧响应并恢复可重新处理状态', async () => {
    const user = userEvent.setup();
    const oldExtraction = deferred<typeof frameResult>();
    mockExtractFrames.mockReturnValueOnce(oldExtraction.promise);
    renderPage();

    await user.upload(screen.getByLabelText('上传原版爆款视频'), new File(['a'], 'video-a.mp4', { type: 'video/mp4' }));
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    expect(await screen.findByText('截帧中')).toBeInTheDocument();

    const transcript = screen.getAllByPlaceholderText('点击上方按钮自动提取，或直接粘贴文案...')[0];
    await user.type(transcript, '人工输入的新文案');
    oldExtraction.resolve(frameResult);

    await waitFor(() => expect(screen.getByText('待处理')).toBeInTheDocument());
    expect(transcript).toHaveValue('人工输入的新文案');
    expect(screen.getByRole('button', { name: '截帧 + 提取文案' })).toBeEnabled();
    expect(screen.queryByText('已提取 1 帧截图')).not.toBeInTheDocument();
    expect(mockTranscribeVideo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
  });

  it('视频 A 重试转录中替换为 B 后忽略 A 的迟到文案', async () => {
    const user = userEvent.setup();
    mockTranscribeVideo.mockRejectedValueOnce(new Error('首次转录失败'));
    renderPage();

    const upload = screen.getByLabelText('上传原版爆款视频');
    await user.upload(upload, new File(['a'], 'video-a.mp4', { type: 'video/mp4' }));
    await user.click(screen.getByRole('button', { name: '截帧 + 提取文案' }));
    expect(await screen.findByRole('button', { name: '重试转录' })).toBeInTheDocument();

    const oldRetry = deferred<{ text: string }>();
    mockTranscribeVideo.mockReturnValueOnce(oldRetry.promise);
    await user.click(screen.getByRole('button', { name: '重试转录' }));
    expect(await screen.findByText('转录中')).toBeInTheDocument();
    await user.upload(upload, new File(['b'], 'video-b.mp4', { type: 'video/mp4' }));
    oldRetry.resolve({ text: '视频 A 的迟到文案' });

    await waitFor(() => expect(screen.getByText('video-b.mp4')).toBeInTheDocument());
    expect(screen.getByText('待处理')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('视频 A 的迟到文案')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始预审' })).toBeDisabled();
  });
});
