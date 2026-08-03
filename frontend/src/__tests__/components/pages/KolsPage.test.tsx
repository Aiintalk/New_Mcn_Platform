import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from 'antd';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockGetKols = vi.fn();
const mockGetKol = vi.fn();
const mockCreateKol = vi.fn();
const mockUpdateKol = vi.fn();

vi.mock('../../../api/kols', () => ({
  getKols: (...args: unknown[]) => mockGetKols(...args),
  getKol: (...args: unknown[]) => mockGetKol(...args),
  createKol: (...args: unknown[]) => mockCreateKol(...args),
  updateKol: (...args: unknown[]) => mockUpdateKol(...args),
  deleteKol: vi.fn(),
  fetchTikhub: vi.fn(),
}));

import KolsPage from '../../../pages/admin/KolsPage';

const jsdomGetComputedStyle = window.getComputedStyle;
vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => jsdomGetComputedStyle(element));

const sampleKol = {
  id: 43,
  name: 'mini兔兔',
  platform: '抖音',
  account_name: 'mini兔兔',
  douyin_id: 'mini43',
  avatar_url: '',
  followers_count: 320000,
  works_count: 128,
  status: 'onboarded' as const,
  owner: '运营甲',
  persona: '真实、克制、有生活经验的朋友',
  content_plan: '围绕职场和轻熟龄穿搭创作',
  style_note: '口语自然',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-03T06:30:00Z',
};

function renderPage() {
  return render(
    <App>
      <MemoryRouter
        initialEntries={['/admin/kols']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/admin/kols" element={<KolsPage />} />
          <Route path="/kol-workspace/:kolId" element={<div>统一人物档案工作台</div>} />
        </Routes>
      </MemoryRouter>
    </App>,
  );
}

describe('KolsPage profile entry closure', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetKols.mockResolvedValue({
      items: [sampleKol],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
    mockGetKol.mockResolvedValue(sampleKol);
  });

  it('创建表单不提供人格档案或内容规划字段', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('mini兔兔');

    await user.click(screen.getByRole('button', { name: '+ 新增红人' }));
    const dialog = await screen.findByRole('dialog', { name: '新增红人' });
    expect(within(dialog).queryByLabelText('人格档案')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('内容规划')).not.toBeInTheDocument();
  });

  it('编辑表单不提供人格档案或内容规划字段', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('mini兔兔');
    await user.click(screen.getByRole('button', { name: '编辑' }));
    const dialog = await screen.findByRole('dialog', { name: /编辑红人/ });
    expect(within(dialog).queryByLabelText('人格档案')).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText('内容规划')).not.toBeInTheDocument();
  });

  it('详情只读展示两项摘要，并跳转同一个红人工作台地址', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: '详情' }));
    await waitFor(() => expect(mockGetKol).toHaveBeenCalledWith(43));
    expect(await screen.findByText(sampleKol.persona)).toBeInTheDocument();
    expect(screen.getByText(sampleKol.content_plan)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存人格档案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存内容规划' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '前往红人工作台编辑' }));
    expect(await screen.findByText('统一人物档案工作台')).toBeInTheDocument();
  });
});
