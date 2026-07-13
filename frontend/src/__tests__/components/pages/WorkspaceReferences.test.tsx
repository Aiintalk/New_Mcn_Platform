import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

const mockGetKolDetail = vi.fn();
const mockCreateReference = vi.fn();
const mockUpdateReference = vi.fn();
const mockDeleteReference = vi.fn();
const mockGetPlayback = vi.fn();
const mockParseDocument = vi.fn();
const mockUploadVideo = vi.fn();

vi.mock('../../../api/materialLibrary', () => ({
  getMaterialLibraryKolDetail: (...args: unknown[]) => mockGetKolDetail(...args),
  flattenKolReferences: (references: Record<string, unknown[]> | unknown[] | { items: unknown[] }) =>
    Array.isArray(references) ? references : ('items' in references ? references.items : Object.values(references).flat()),
  createKolReference: (...args: unknown[]) => mockCreateReference(...args),
  updateKolReference: (...args: unknown[]) => mockUpdateReference(...args),
  deleteKolReference: (...args: unknown[]) => mockDeleteReference(...args),
  getKolReferenceVideoPlayback: (...args: unknown[]) => mockGetPlayback(...args),
  parseKolReferenceDocument: (...args: unknown[]) => mockParseDocument(...args),
  uploadKolReferenceVideo: (...args: unknown[]) => mockUploadVideo(...args),
}));

import WorkspaceReferences from '../../../pages/operator/workspace/WorkspaceReferences';

const detail = {
  id: 1,
  name: '孙知羽',
  account_name: 'sun',
  category: '美妆',
  follower_count: null,
  persona: '',
  content_plan: '',
  references: {
    '红人爆款文案': [{
      id: 10,
      title: '夏季护肤心得',
      likes: 50000,
      source: '抖音',
      type: '红人爆款文案',
      content: '夏天的护肤要点。',
      data_description: '5 万点赞，完播率 28%',
      document_name: '夏季脚本.docx',
      document_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      document_size: 1024,
      has_video: true,
      video_name: 'summer.mp4',
      video_content_type: 'video/mp4',
      video_size: 2048,
      created_at: '2026-07-14T00:00:00Z',
    }],
    '红人喜欢的内容': [],
    '风格参考': [],
    '千川爆款文案': [],
    '千川喜欢的内容': [],
    '千川风格参考': [],
  },
};

function renderPage() {
  return render(<App><WorkspaceReferences kolId={1} /></App>);
}

describe('WorkspaceReferences', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetKolDetail.mockResolvedValue(detail);
    mockGetPlayback.mockResolvedValue({ url: 'https://signed.example/video.mp4', expires_in: 900 });
    mockCreateReference.mockResolvedValue({ ...detail.references['红人爆款文案'][0], id: 11 });
    mockUpdateReference.mockResolvedValue(detail.references['红人爆款文案'][0]);
    mockDeleteReference.mockResolvedValue({});
    mockParseDocument.mockResolvedValue({ text: '解析后的正文', document_name: '脚本.docx', document_type: 'application/docx', document_size: 123 });
    mockUploadVideo.mockResolvedValue(detail.references['红人爆款文案'][0]);
  });

  it('loads only the current kol materials and shows their media summary', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => expect(mockGetKolDetail).toHaveBeenCalledWith(1));
    expect(screen.getByText('素材库')).toBeInTheDocument();
    await user.click(screen.getByText('红人爆款文案'));
    expect(screen.getByText('夏季护肤心得')).toBeInTheDocument();
    expect(screen.getByText('5 万点赞，完播率 28%')).toBeInTheDocument();
    expect(screen.getByText(/有视频/)).toBeInTheDocument();
  });

  it('gets a short-lived playback URL only after the operator expands a video material', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('红人爆款文案'));
    await user.click(await screen.findByRole('button', { name: '展开' }));

    await waitFor(() => expect(mockGetPlayback).toHaveBeenCalledWith(1, 10));
    expect(await screen.findByText(/summer\.mp4/)).toBeInTheDocument();
  });

  it('keeps the existing video when an operator only edits text metadata', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('红人爆款文案'));
    await user.click(await screen.findByRole('button', { name: '编辑' }));
    await user.clear(screen.getByLabelText('数据说明'));
    await user.type(screen.getByLabelText('数据说明'), '更新后的数据说明');
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(mockUpdateReference).toHaveBeenCalledWith(
      1, 10, expect.objectContaining({ data_description: '更新后的数据说明' }),
    ));
    expect(mockUploadVideo).not.toHaveBeenCalled();
  });

  it('puts parsed document text into the editable script body before save', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('红人爆款文案'));
    await user.click(screen.getByRole('button', { name: '添加素材' }));
    const input = screen.getByLabelText('上传脚本文档');
    fireEvent.change(input, { target: { files: [new File(['source'], '脚本.docx', { type: 'application/docx' })] } });

    await waitFor(() => expect(mockParseDocument).toHaveBeenCalledWith(1, expect.any(File)));
    expect(await screen.findByDisplayValue('解析后的正文')).toBeInTheDocument();
  });

  it('shows the 500MB server limit and prevents an oversized video upload', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('红人爆款文案'));
    await user.click(screen.getByRole('button', { name: '编辑' }));
    expect(screen.getByText(/最大 500MB/)).toBeInTheDocument();

    const oversizedVideo = new File(['video'], 'oversized.mp4', { type: 'video/mp4' });
    Object.defineProperty(oversizedVideo, 'size', { value: 500 * 1024 * 1024 + 1 });
    fireEvent.change(screen.getByLabelText('视频原片'), { target: { files: [oversizedVideo] } });
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => expect(mockUpdateReference).toHaveBeenCalled());
    expect(mockUploadVideo).not.toHaveBeenCalled();
  });
});
