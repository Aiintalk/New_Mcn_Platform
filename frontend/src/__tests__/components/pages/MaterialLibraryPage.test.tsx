import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// Mock API — operator
const mockGetKols = vi.fn();
const mockGetKolDetail = vi.fn();
const mockUpdateKolProfile = vi.fn();
const mockCreateKolReference = vi.fn();
const mockDeleteKolReference = vi.fn();
const mockGetKolIntake = vi.fn();
const mockGenerateSoul = vi.fn();

vi.mock('../../../api/materialLibrary', () => ({
  getMaterialLibraryKols: (...args: unknown[]) => mockGetKols(...args),
  getMaterialLibraryKolDetail: (...args: unknown[]) => mockGetKolDetail(...args),
  updateKolProfile: (...args: unknown[]) => mockUpdateKolProfile(...args),
  createKolReference: (...args: unknown[]) => mockCreateKolReference(...args),
  deleteKolReference: (...args: unknown[]) => mockDeleteKolReference(...args),
  getKolIntake: (...args: unknown[]) => mockGetKolIntake(...args),
  generateSoul: (...args: unknown[]) => mockGenerateSoul(...args),
  getMaterialLibraryConfigs: vi.fn(),
  updateMaterialLibraryConfig: vi.fn(),
}));

// Mock antd message
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: { success: vi.fn(), error: vi.fn() },
  };
});

import MaterialLibraryPage from '../../../pages/operator/MaterialLibraryPage';

const sampleKols = [
  {
    id: 1,
    name: '孙静',
    account_name: 'sunjing',
    category: '美妆',
    follower_count: 1200000,
    has_persona: true,
    has_content_plan: false,
    reference_count: 3,
    has_intake: true,
    updated_at: '2026-06-20T10:00:00Z',
  },
  {
    id: 2,
    name: '陶然',
    account_name: 'taoran',
    category: '科技',
    follower_count: 800000,
    has_persona: false,
    has_content_plan: false,
    reference_count: 0,
    has_intake: false,
    updated_at: null,
  },
];

const sampleDetail = {
  id: 1,
  name: '孙静',
  account_name: 'sunjing',
  category: '美妆',
  follower_count: 1200000,
  persona: '我是孙静，美妆博主',
  content_plan: '',
  references: {
    '红人爆款文案': [
      { id: 10, title: '夏季护肤心得', likes: 50000, source: '抖音', content: '夏天的护肤要点...', created_at: '2026-06-01' },
    ],
    '风格参考': [],
    '红人喜欢的内容': [],
    '千川爆款文案': [],
    '千川喜欢的内容': [],
    '千川风格参考': [],
  },
};

function renderWithApp(ui: React.ReactElement) {
  return render(<App>{ui}</App>);
}

type UserInstance = ReturnType<typeof userEvent.setup>;

async function openSelectAndPick(user: UserInstance, optionText: RegExp, selectIndex = 0): Promise<void> {
  await waitFor(() => {
    const selectors = document.querySelectorAll('.ant-select-selector');
    expect(selectors.length).toBeGreaterThan(selectIndex);
  });
  const selectSelector = document.querySelectorAll('.ant-select-selector')[selectIndex] as HTMLElement;
  await act(async () => {
    fireEvent.mouseDown(selectSelector);
  });
  await waitFor(() => screen.getByText(optionText));
  await user.click(screen.getByText(optionText));
}

// ---------------------------------------------------------------------------
// MaterialLibraryPage Tests
// ---------------------------------------------------------------------------
describe('MaterialLibraryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetKols.mockResolvedValue(sampleKols);
    mockGetKolDetail.mockResolvedValue(sampleDetail);
    mockUpdateKolProfile.mockResolvedValue({ success: true });
    mockCreateKolReference.mockResolvedValue({ id: 99 });
    mockDeleteKolReference.mockResolvedValue({ success: true });
    mockGenerateSoul.mockResolvedValue({ soul_md: '# 孙静人格档案\nAI 生成的初稿' });
  });

  // Test 1: 左右分栏渲染 — 红人列表 + 详情区
  it('renders left kol list and right detail tabs', async () => {
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => {
      expect(mockGetKols).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getByText('孙静')).toBeInTheDocument();
      expect(screen.getByText('素材库')).toBeInTheDocument();
      expect(screen.getByText('人格档案')).toBeInTheDocument();
      expect(screen.getByText('内容规划')).toBeInTheDocument();
      expect(screen.getByText('入驻信息')).toBeInTheDocument();
    });
  });

  // Test 2: 选中红人加载详情
  it('loads detail when kol is selected', async () => {
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => expect(mockGetKols).toHaveBeenCalled());
    await waitFor(() => expect(mockGetKolDetail).toHaveBeenCalledWith(1));

    // persona 内容应在文本区显示
    await waitFor(() => {
      expect(screen.getByDisplayValue('我是孙静，美妆博主')).toBeInTheDocument();
    });
  });

  // Test 3: 保存人格档案
  it('calls updateKolProfile when save persona clicked', async () => {
    const user = userEvent.setup();
    mockUpdateKolProfile.mockResolvedValue({ success: true });
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByDisplayValue('我是孙静，美妆博主'));

    // 人格档案 Tab 默认激活，找保存按钮（同 Tab 内有两个：人格档案 + 内容规划，但内容规划 Tab 隐藏）
    const saveButtons = screen.getAllByRole('button').filter((b) => /^保\s*存$/.test(b.textContent || ''));
    expect(saveButtons.length).toBeGreaterThan(0);
    await user.click(saveButtons[0]);

    await waitFor(() => {
      expect(mockUpdateKolProfile).toHaveBeenCalledWith(1, expect.objectContaining({ persona: expect.any(String) }));
    });
  });

  // Test 4: 切到内容规划 Tab
  it('switches to content plan tab', async () => {
    const user = userEvent.setup();
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByText('内容规划'));
    await user.click(screen.getByText('内容规划'));

    await waitFor(() => {
      expect(screen.getByText('内容规划（content-plan.md）')).toBeInTheDocument();
    });
  });

  // Test 5: 切到参考素材 Tab，显示分组素材
  it('renders grouped references in references tab', async () => {
    const user = userEvent.setup();
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByRole('tab', { name: /参考素材/ }));
    await user.click(screen.getByRole('tab', { name: /参考素材/ }));

    await waitFor(() => {
      expect(screen.getByText('夏季护肤心得')).toBeInTheDocument();
    });
  });

  // Test 6: 添加素材弹窗
  it('opens add reference modal when button clicked', async () => {
    const user = userEvent.setup();
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByRole('tab', { name: /参考素材/ }));
    await user.click(screen.getByRole('tab', { name: /参考素材/ }));

    // 点添加素材按钮
    const addBtn = await waitFor(() => {
      const btn = screen.getAllByRole('button').find((b) => /添加素材/.test(b.textContent || ''));
      if (!btn) throw new Error('add button not found');
      return btn;
    });
    await user.click(addBtn);

    await waitFor(() => {
      expect(screen.getByText('添加参考素材')).toBeInTheDocument();
    });
  });

  // Test 7: 添加素材提交
  it('calls createKolReference on submit', async () => {
    const user = userEvent.setup();
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByRole('tab', { name: /参考素材/ }));
    await user.click(screen.getByRole('tab', { name: /参考素材/ }));

    const addBtn = await waitFor(() => {
      const btn = screen.getAllByRole('button').find((b) => /添加素材/.test(b.textContent || ''));
      if (!btn) throw new Error('add button not found');
      return btn;
    });
    await user.click(addBtn);

    await waitFor(() => screen.getByText('添加参考素材'));

    // 选类型
    await openSelectAndPick(user, /人设仿写素材 — 红人爆款文案/);

    // 填标题
    await user.type(screen.getByPlaceholderText('视频/文案标题'), '新素材标题');

    // 填正文
    await user.type(screen.getByPlaceholderText('粘贴文案正文'), '这是文案正文内容');

    // 点确定 — AntD 会自动给两个中文字之间插入空格（"添加"→"添 加"）
    const okBtn = screen.getAllByRole('button').find((b) => /^添\s*加$/.test(b.textContent || ''));
    expect(okBtn).toBeTruthy();
    if (okBtn) await user.click(okBtn);

    await waitFor(() => {
      expect(mockCreateKolReference).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ title: '新素材标题', content: '这是文案正文内容' }),
      );
    });
  });

  // Test 8: 删除素材（AntD Popconfirm 默认 OK 按钮文本 = "OK"，未配置 zhCN locale）
  it('calls deleteKolReference when delete confirmed', async () => {
    const user = userEvent.setup();
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByRole('tab', { name: /参考素材/ }));
    await user.click(screen.getByRole('tab', { name: /参考素材/ }));

    await waitFor(() => screen.getByText('夏季护肤心得'));

    // 点击删除按钮
    const deleteButtons = screen.getAllByRole('button').filter((b) => /^删\s*除$/.test(b.textContent || ''));
    expect(deleteButtons.length).toBeGreaterThan(0);
    await user.click(deleteButtons[0]);

    // 等待 Popconfirm 弹出，OK 按钮文本是 "OK"
    const confirmBtn = await waitFor(() => {
      const btn = screen.getAllByRole('button').find((b) => b.textContent === 'OK');
      if (!btn) throw new Error('OK button not found');
      return btn;
    });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(mockDeleteKolReference).toHaveBeenCalled();
    });
  });

  // Test 9: 从入驻问卷生成 soul.md（无 persona → 直接调用，不走 Modal.confirm）
  // 注：有 persona 时弹 Modal.confirm，但 AntD v5 静态方法在测试环境无法挂载，
  // 改测无 persona 的直调分支（doGenerate() 内部调用 generateSoul API）。
  it('calls generateSoul directly when persona is empty', async () => {
    const user = userEvent.setup();
    // 覆盖 detail，让 persona 为空字符串
    mockGetKolDetail.mockResolvedValue({
      ...sampleDetail,
      persona: '',
      references: {
        '红人爆款文案': [], '风格参考': [], '红人喜欢的内容': [],
        '千川爆款文案': [], '千川喜欢的内容': [], '千川风格参考': [],
      },
    });
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => {
      // persona 文本区为空时仍能找到（getByDisplayValue 找不到空值，改查 placeholder）
      const textarea = screen.getByPlaceholderText(/暂无人格档案/);
      expect(textarea).toBeInTheDocument();
    });

    const genBtn = screen.getAllByRole('button').find((b) => /从入驻问卷生成/.test(b.textContent || ''));
    expect(genBtn).toBeTruthy();
    if (genBtn) await user.click(genBtn);

    // 无 persona → 不弹 Modal.confirm，直接调 doGenerate
    await waitFor(() => {
      expect(mockGenerateSoul).toHaveBeenCalledWith(1);
    });
  });

  // Test 10: 切到入驻信息 Tab 加载问卷
  it('loads intake data when intake tab clicked', async () => {
    const user = userEvent.setup();
    mockGetKolIntake.mockResolvedValue({
      source: 'operator_session',
      messages: [{ role: 'user', content: '你好' }, { role: 'assistant', content: '你好，请介绍一下自己' }],
      ai_report: '这是一份 AI 分析报告',
      report_status: 'completed',
      created_at: '2026-06-15T10:00:00Z',
    });

    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => screen.getByText('入驻信息'));
    await user.click(screen.getByText('入驻信息'));

    // 点击"加载入驻问卷"按钮
    await waitFor(() => {
      const loadBtn = screen.getAllByRole('button').find((b) => /加载入驻问卷/.test(b.textContent || ''));
      if (loadBtn) loadBtn.click();
    });

    await waitFor(() => {
      expect(mockGetKolIntake).toHaveBeenCalledWith(1);
    });
  });

  // Test 11: 搜索红人
  it('triggers kol list reload on search', async () => {
    const user = userEvent.setup();
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => expect(mockGetKols).toHaveBeenCalled());

    // 在搜索框输入文字
    const searchInput = screen.getByPlaceholderText('搜索红人名');
    await user.type(searchInput, '孙');

    // 搜索值变化后再次调用（useEffect 依赖）
    await waitFor(() => {
      expect(mockGetKols).toHaveBeenCalledWith('孙');
    });
  });

  // Test 12: 空列表
  it('renders empty state when no kols', async () => {
    mockGetKols.mockResolvedValue([]);
    renderWithApp(<MaterialLibraryPage />);

    await waitFor(() => {
      expect(screen.getByText('暂无红人')).toBeInTheDocument();
    });
  });
});
