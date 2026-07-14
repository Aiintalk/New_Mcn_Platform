import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

const mockAnalyzeFilm = vi.fn();
const mockSaveFilmReport = vi.fn();
const mockExportFilmReport = vi.fn();

vi.mock('../../../api/filmReview', () => ({
  analyzeFilm: (...args: unknown[]) => mockAnalyzeFilm(...args),
  saveFilmReport: (...args: unknown[]) => mockSaveFilmReport(...args),
  exportFilmReport: (...args: unknown[]) => mockExportFilmReport(...args),
}));

import { FilmReviewModule } from '../../../pages/operator/FilmReviewPage';

describe('FilmReviewModule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows two complete-video upload cards and the backend size instruction', () => {
    render(<App><FilmReviewModule kolId={7} /></App>);

    expect(screen.getByText('原片')).toBeInTheDocument();
    expect(screen.getByText('已剪辑成片')).toBeInTheDocument();
    expect(screen.getByText('支持 mp4、mov。建议 500MB 以内，实际服务端限制为 500MB。')).toBeInTheDocument();
    expect(screen.getByTestId('film-file-original')).toHaveAttribute('accept', '.mp4,.mov,video/mp4,video/quicktime');
    expect(screen.getByTestId('film-file-edited')).toHaveAttribute('accept', '.mp4,.mov,video/mp4,video/quicktime');
  });

  it('keeps selected files visible when the complete-video upload and analysis fail', async () => {
    const user = userEvent.setup();
    mockAnalyzeFilm.mockResolvedValueOnce(new Response(JSON.stringify({ message: '服务暂不可用' }), { status: 503 }));
    render(<App><FilmReviewModule kolId={7} /></App>);

    const original = new File(['video'], 'origin.mp4', { type: 'video/mp4' });
    const edited = new File(['video'], 'edited.mov', { type: 'video/quicktime' });
    await user.upload(screen.getByTestId('film-file-original'), original);
    await user.upload(screen.getByTestId('film-file-edited'), edited);
    await user.click(screen.getByRole('button', { name: /开始剪辑分析/ }));

    expect(await screen.findByText('origin.mp4')).toBeInTheDocument();
    expect((await screen.findAllByRole('alert')).length).toBeGreaterThanOrEqual(2);
    expect(mockAnalyzeFilm).toHaveBeenCalledWith(7, original, edited);
  });

  it('sends both selected complete videos, renders the streamed report, and saves it with its task id', async () => {
    const user = userEvent.setup();
    mockSaveFilmReport.mockResolvedValue({ output_id: 9 });
    mockAnalyzeFilm.mockResolvedValue(new Response(
      'event: status\ndata: {"message":"正在上传两条完整视频"}\n\nevent: status\ndata: {"message":"Gemini 正在读取两条完整视频..."}\n\nevent: report\ndata: {"text":"# 三维评分："}\n\nevent: report\ndata: {"text":"88"}\n\n',
      { headers: { 'X-Task-Id': '42' } },
    ));
    render(<App><FilmReviewModule kolId={7} /></App>);

    const original = new File(['origin'], 'origin.mp4', { type: 'video/mp4' });
    const edited = new File(['edited'], 'edited.mov', { type: 'video/quicktime' });
    await user.upload(screen.getByTestId('film-file-original'), original);
    await user.upload(screen.getByTestId('film-file-edited'), edited);
    await user.click(screen.getByRole('button', { name: /开始剪辑分析/ }));

    await waitFor(() => expect(mockAnalyzeFilm).toHaveBeenCalledWith(7, original, edited));
    expect(await screen.findByText('正在读取两条完整视频')).toBeInTheDocument();
    expect(await screen.findByText(/三维评分：88/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /保存报告/ }));
    expect(mockSaveFilmReport).toHaveBeenCalledWith({
      task_id: 42,
      report: '# 三维评分：88',
      original_filename: 'origin.mp4',
      edited_filename: 'edited.mov',
    });
  });

  it('marks the selected files failed and does not offer save or export after an SSE error event', async () => {
    const user = userEvent.setup();
    mockAnalyzeFilm.mockResolvedValue(new Response(
      'event: report\ndata: {"text":"# 部分报告"}\n\nevent: error\ndata: {"message":"Gemini 服务超时"}\n\nevent: failed\ndata: {"task_id":42}\n\n',
      { headers: { 'X-Task-Id': '42' } },
    ));
    render(<App><FilmReviewModule kolId={7} /></App>);

    await user.upload(screen.getByTestId('film-file-original'), new File(['origin'], 'origin.mp4', { type: 'video/mp4' }));
    await user.upload(screen.getByTestId('film-file-edited'), new File(['edited'], 'edited.mov', { type: 'video/quicktime' }));
    await user.click(screen.getByRole('button', { name: /开始剪辑分析/ }));

    expect((await screen.findAllByText('分析失败，可重试')).length).toBe(2);
    expect(screen.getAllByText(/Gemini 服务超时/).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /保存报告/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /导出办公文档/ })).not.toBeInTheDocument();
  });
});
