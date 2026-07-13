import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// ── Mock API ─────────────────────────────────────────────────────────────────

const mockGetSessions = vi.fn();
const mockSaveSession = vi.fn();
const mockDeleteSession = vi.fn();
const mockParseFiles = vi.fn();
const mockAnalyzeStream = vi.fn();
const mockExportWord = vi.fn();

vi.mock('../../../api/retrospective', () => ({
  getSessions:   (...args: unknown[]) => mockGetSessions(...args),
  saveSession:   (...args: unknown[]) => mockSaveSession(...args),
  deleteSession: (...args: unknown[]) => mockDeleteSession(...args),
  parseFiles:    (...args: unknown[]) => mockParseFiles(...args),
  analyzeStream: (...args: unknown[]) => mockAnalyzeStream(...args),
  exportWord:    (...args: unknown[]) => mockExportWord(...args),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

// ── 样本数据 ──────────────────────────────────────────────────────────────────

const session1 = {
  id: 1,
  kol_id: 1,
  title: '0608 Biodance 直播',
  status: 'done' as const,
  live_data: '直播数据文本',
  material_data: null,
  review_text: null,
  live_script: null,
  material_scripts: null,
  result: '## 直播复盘\n本场直播效果良好',
  created_at: '2026-06-08T15:30:00Z',
  updated_at: '2026-06-08T15:30:00Z',
};

const session2 = {
  id: 2,
  kol_id: 1,
  title: '0605 某场直播',
  status: 'draft' as const,
  live_data: null,
  material_data: null,
  review_text: null,
  live_script: null,
  material_scripts: null,
  result: null,
  created_at: '2026-06-05T12:00:00Z',
  updated_at: '2026-06-05T12:00:00Z',
};

const samplePagination = {
  page: 1,
  page_size: 20,
  total: 2,
  total_pages: 1,
};

// ── 渲染 helper ───────────────────────────────────────────────────────────────

import WorkspaceRetrospective from '../../../pages/operator/workspace/WorkspaceRetrospective';

function renderModule(kolId = 1) {
  return render(
    <App>
      <WorkspaceRetrospective kolId={kolId} />
    </App>,
  );
}

// ─────────────────────────────────────────────────────────────────────────────

describe('WorkspaceRetrospective', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Test 1: 渲染历史列表 ──────────────────────────────────────────────────────
  it('Test 1: 渲染历史列表（mock getSessions 返回 2 条）', async () => {
    mockGetSessions.mockResolvedValue({
      items: [session1, session2],
      pagination: samplePagination,
    });

    renderModule();

    // 等待列表加载完成
    await waitFor(() => {
      expect(screen.getByText('0608 Biodance 直播')).toBeInTheDocument();
      expect(screen.getByText('0605 某场直播')).toBeInTheDocument();
    });

    // 验证状态 badge
    expect(screen.getByText('已完成')).toBeInTheDocument();
    expect(screen.getByText('草稿')).toBeInTheDocument();

    // 验证 getSessions 被调用
    expect(mockGetSessions).toHaveBeenCalledWith(1, 1);
  });

  // ── Test 2: 点击「+ 新建复盘」→ 切换到编辑视图 ──────────────────────────────────
  it('Test 2: 点击「+ 新建复盘」→ 切换到编辑视图', async () => {
    mockGetSessions.mockResolvedValue({
      items: [session1, session2],
      pagination: samplePagination,
    });

    renderModule();

    await waitFor(() => {
      expect(screen.getByText('新建复盘')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText('新建复盘'));

    // 进入编辑视图后显示场次标题输入框
    expect(screen.getByTestId('title-input')).toBeInTheDocument();
    // 显示操作按钮
    expect(screen.getByTestId('save-draft-btn')).toBeInTheDocument();
    expect(screen.getByTestId('analyze-btn')).toBeInTheDocument();
  });

  it('逐份保存千川素材脚本的文件名和解析正文', async () => {
    mockGetSessions.mockResolvedValue({ items: [], pagination: { ...samplePagination, total: 0, total_pages: 0 } });
    mockParseFiles.mockResolvedValue({ files: [
      { name: '第一份.txt', text: '第一份正文' },
      { name: '第二份.txt', text: '第二份正文' },
    ] });
    renderModule();
    await screen.findByText('新建复盘');
    const user = userEvent.setup();
    await user.click(screen.getByText('新建复盘'));
    const input = screen.getByTestId('file-input-material_scripts');
    await user.upload(input, [new File(['one'], '第一份.txt', { type: 'text/plain' }), new File(['two'], '第二份.txt', { type: 'text/plain' })]);
    expect(await screen.findByDisplayValue('第一份正文')).toBeInTheDocument();
    expect(screen.getByDisplayValue('第二份正文')).toBeInTheDocument();
  });

  // ── Test 3: 编辑视图 - 标题输入 + 保存草稿 ────────────────────────────────────
  it('Test 3: 编辑视图：标题输入 + 「保存草稿」按钮', async () => {
    mockGetSessions.mockResolvedValue({
      items: [],
      pagination: { ...samplePagination, total: 0, total_pages: 0 },
    });

    const savedSession = {
      ...session2,
      id: 99,
      title: '测试复盘场次',
      status: 'draft' as const,
    };
    mockSaveSession.mockResolvedValue(savedSession);

    renderModule();

    // 进入编辑视图
    await waitFor(() => {
      expect(screen.getByText('新建复盘')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText('新建复盘'));

    // 输入标题
    const titleInput = screen.getByTestId('title-input');
    await user.type(titleInput, '测试复盘场次');
    expect(titleInput).toHaveValue('测试复盘场次');

    // 点击保存草稿
    await user.click(screen.getByTestId('save-draft-btn'));

    await waitFor(() => {
      expect(mockSaveSession).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ title: '测试复盘场次', status: 'draft' }),
      );
    });
  });

  // ── Test 4: 「开始复盘分析」触发 analyzeStream → 流式文本出现 ──────────────────
  it('Test 4: 「开始复盘分析」触发 analyzeStream（mock）→ 流式文本出现', async () => {
    mockGetSessions.mockResolvedValue({
      items: [],
      pagination: { ...samplePagination, total: 0, total_pages: 0 },
    });

    const draftSession = { ...session2, id: 42, title: '流式测试场次', status: 'draft' as const };
    const doneSession = { ...draftSession, status: 'done' as const, result: '## 复盘结果\n分析完成' };

    mockSaveSession
      .mockResolvedValueOnce(draftSession)   // 第一次：保存草稿
      .mockResolvedValueOnce(doneSession);   // 第二次：保存最终结果

    // mock analyzeStream：调用 onDelta 两次，然后返回最终文本
    mockAnalyzeStream.mockImplementation(
      async (_kolId: number, _sessionId: number, onDelta: (text: string) => void) => {
        onDelta('## 复盘结果\n');
        onDelta('## 复盘结果\n分析完成');
        return '## 复盘结果\n分析完成';
      },
    );

    renderModule();

    await waitFor(() => {
      expect(screen.getByText('新建复盘')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByText('新建复盘'));

    // 输入标题
    const titleInput = screen.getByTestId('title-input');
    await user.type(titleInput, '流式测试场次');

    // 点击开始复盘分析
    await act(async () => {
      await user.click(screen.getByTestId('analyze-btn'));
    });

    // 验证 analyzeStream 被调用
    await waitFor(() => {
      expect(mockAnalyzeStream).toHaveBeenCalledWith(1, 42, expect.any(Function));
    });

    // 分析完成后切换到详情视图，显示结果
    await waitFor(() => {
      expect(screen.getByTestId('export-word-btn')).toBeInTheDocument();
    });
  });

  // ── Test 5: 详情视图渲染 result 文本 + 显示「导出 Word」按钮 ─────────────────────
  it('Test 5: 详情视图：渲染 result 文本 + 显示「导出 Word」按钮', async () => {
    mockGetSessions.mockResolvedValue({
      items: [session1, session2],
      pagination: samplePagination,
    });

    renderModule();

    // 等待列表加载
    await waitFor(() => {
      expect(screen.getByText('0608 Biodance 直播')).toBeInTheDocument();
    });

    // 点击已完成的卡片（有 result，直接进入详情视图）
    const user = userEvent.setup();
    await user.click(screen.getByTestId('session-card-1'));

    // 验证详情视图中有「导出 Word」按钮
    await waitFor(() => {
      expect(screen.getByTestId('export-word-btn')).toBeInTheDocument();
    });

    // 验证「复制全文」按钮
    expect(screen.getByTestId('copy-btn')).toBeInTheDocument();

    // 验证「重新复盘」按钮
    expect(screen.getByTestId('reanalyze-btn')).toBeInTheDocument();

    // 验证 result 文本渲染（Markdown h2 标题）
    expect(screen.getByText('直播复盘')).toBeInTheDocument();
  });

  // ── Test 6: 删除按钮触发 deleteSession ──────────────────────────────────────
  it('Test 6: 删除按钮触发 deleteSession', async () => {
    mockGetSessions.mockResolvedValue({
      items: [session1, session2],
      pagination: samplePagination,
    });
    mockDeleteSession.mockResolvedValue({ id: 1 });

    renderModule();

    await waitFor(() => {
      expect(screen.getByTestId('delete-btn-1')).toBeInTheDocument();
    });

    const user = userEvent.setup();

    // 点击删除按钮触发 Popconfirm
    await user.click(screen.getByTestId('delete-btn-1'));

    // AntD Popconfirm 渲染到 portal，用 document.body 查找确认按钮
    await waitFor(() => {
      const confirmBtn = document.body.querySelector('.ant-popconfirm .ant-btn-primary');
      expect(confirmBtn).not.toBeNull();
    });

    const confirmBtn = document.body.querySelector('.ant-popconfirm .ant-btn-primary') as HTMLElement;
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(mockDeleteSession).toHaveBeenCalledWith(1, 1);
    });
  });
});
