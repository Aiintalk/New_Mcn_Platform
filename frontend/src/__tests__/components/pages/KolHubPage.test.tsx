import { App } from 'antd';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGetKols, authRole } = vi.hoisted(() => ({ mockGetKols: vi.fn(), authRole: { value: 'operator' } }));
vi.mock('../../../api/kols', () => ({ getKols: mockGetKols, getKol: vi.fn(), fetchTikhub: vi.fn() }));
vi.mock('../../../store/authStore', () => ({
  useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authRole.value } }),
}));

import KolHubPage from '../../../pages/operator/KolHubPage';

function renderPage() {
  return render(
    <App><MemoryRouter initialEntries={['/kol-hub']}><Routes>
      <Route path="/kol-hub" element={<KolHubPage />} />
      <Route path="/workspace/persona-positioning" element={<div>人格定位页</div>} />
      <Route path="/admin/kols" element={<div>红人管理页</div>} />
    </Routes></MemoryRouter></App>,
  );
}

describe('KolHubPage 入口权限语义', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authRole.value = 'operator';
    mockGetKols.mockResolvedValue({ items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } });
  });

  it('运营只看到人格定位入口，不再承诺新增红人', async () => {
    const user = userEvent.setup();
    renderPage();
    expect(screen.queryByRole('button', { name: /新增红人/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '前往红人管理新增' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '人格定位' }));
    expect(await screen.findByText('人格定位页')).toBeInTheDocument();
  });

  it('管理员额外看到红人管理新增入口', async () => {
    const user = userEvent.setup();
    authRole.value = 'admin';
    renderPage();
    await user.click(screen.getByRole('button', { name: '前往红人管理新增' }));
    expect(await screen.findByText('红人管理页')).toBeInTheDocument();
  });
});
