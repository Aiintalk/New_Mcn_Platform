import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { App } from 'antd';

// ── Mock API ──────────────────────────────────────────────────────────────────
const mockGetWorkspaceDashboard    = vi.fn();
const mockGetBenchmarks            = vi.fn();
const mockCreateBenchmark          = vi.fn();
const mockUpdateBenchmark          = vi.fn();
const mockDeleteBenchmark          = vi.fn();
const mockGetActiveProducts        = vi.fn();
const mockUpdateActiveProducts     = vi.fn();
const mockGetPersonaDetails        = vi.fn();
const mockUpdatePersonaDetails     = vi.fn();
const mockGetMaterialLibraryKolDetail = vi.fn();

vi.mock('../../../api/kolWorkspace', () => ({
  getWorkspaceDashboard:  (...args: unknown[]) => mockGetWorkspaceDashboard(...args),
  getBenchmarks:          (...args: unknown[]) => mockGetBenchmarks(...args),
  createBenchmark:        (...args: unknown[]) => mockCreateBenchmark(...args),
  updateBenchmark:        (...args: unknown[]) => mockUpdateBenchmark(...args),
  deleteBenchmark:        (...args: unknown[]) => mockDeleteBenchmark(...args),
  getActiveProducts:      (...args: unknown[]) => mockGetActiveProducts(...args),
  updateActiveProducts:   (...args: unknown[]) => mockUpdateActiveProducts(...args),
  getPersonaDetails:      (...args: unknown[]) => mockGetPersonaDetails(...args),
  updatePersonaDetails:   (...args: unknown[]) => mockUpdatePersonaDetails(...args),
}));

const mockGetQianchuanProducts     = vi.fn();
const mockCreateQianchuanProduct   = vi.fn();
const mockUpdateQianchuanProduct   = vi.fn();
const mockDeleteQianchuanProduct   = vi.fn();

vi.mock('../../../api/qianchuanProducts', () => ({
  getQianchuanProducts:   (...args: unknown[]) => mockGetQianchuanProducts(...args),
  createQianchuanProduct: (...args: unknown[]) => mockCreateQianchuanProduct(...args),
  updateQianchuanProduct: (...args: unknown[]) => mockUpdateQianchuanProduct(...args),
  deleteQianchuanProduct: (...args: unknown[]) => mockDeleteQianchuanProduct(...args),
}));

vi.mock('../../../api/materialLibrary', () => ({
  getMaterialLibraryKolDetail: (...args: unknown[]) => mockGetMaterialLibraryKolDetail(...args),
  flattenKolReferences: (references: Record<string, unknown[]> | unknown[] | { items: unknown[] }) =>
    Array.isArray(references) ? references : ('items' in references ? references.items : Object.values(references).flat()),
  createKolReference: vi.fn(),
  updateKolReference: vi.fn(),
  deleteKolReference: vi.fn(),
  getKolReferenceVideoPlayback: vi.fn(),
  parseKolReferenceDocument: vi.fn(),
  uploadKolReferenceVideo: vi.fn(),
}));

// Mock APIs used by tool Modules
vi.mock('../../../api/qianchuanWriter', () => ({
  getPersonas: vi.fn().mockResolvedValue([]),
  parseFile: vi.fn(),
  chatStream: vi.fn(),
  saveOutput: vi.fn(),
  exportWord: vi.fn(),
}));

vi.mock('../../../api/seedingWriter', () => ({
  getPersonas: vi.fn().mockResolvedValue([]),
  getReferences: vi.fn().mockResolvedValue([]),
  createReference: vi.fn(),
  importReferenceFromDouyin: vi.fn(),
  deleteReference: vi.fn(),
  getProducts: vi.fn().mockResolvedValue({ items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } }),
  createProduct: vi.fn(),
  updateProduct: vi.fn(),
  deleteProduct: vi.fn(),
  parseProductDocument: vi.fn(),
  extractSellingPointsStream: vi.fn(),
  fetchVideo: vi.fn(),
  submitTranscribe: vi.fn(),
  pollTranscribe: vi.fn(),
  analyzeStructureStream: vi.fn(),
  aiRecommendStream: vi.fn(),
  chatStream: vi.fn(),
  saveOutput: vi.fn(),
  exportWord: vi.fn(),
}));

vi.mock('../../../api/personaWriter', () => ({
  getPersonas: vi.fn().mockResolvedValue([]),
  fetchVideo: vi.fn(),
  evaluateOpeningStream: vi.fn(),
  analyzeStructureStream: vi.fn(),
  chatStream: vi.fn(),
  saveOutput: vi.fn(),
  exportWord: vi.fn(),
}));

vi.mock('../../../api/livestreamWriter', () => ({
  getLivestreamWriterConfig: vi.fn().mockResolvedValue({ generate_prompt: '', iterate_prompt: '', model_id: '' }),
  getKolPersonas: vi.fn().mockResolvedValue({ personas: [] }),
  parseFile: vi.fn(),
  chatStream: vi.fn(),
}));

vi.mock('../../../api/livestreamReview', () => ({
  parseFile: vi.fn(),
  generateStream: vi.fn(),
  saveReport: vi.fn(),
  getOutputs: vi.fn().mockResolvedValue({ items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } }),
}));

// Mock request.ts for WorkspaceReferences
vi.mock('../../../api/request', () => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({ id: 1 }),
  put: vi.fn().mockResolvedValue({}),
  del: vi.fn().mockResolvedValue({}),
  patch: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

// jsdom 不支持 scrollIntoView
Element.prototype.scrollIntoView = vi.fn();

import KolWorkspacePage from '../../../pages/operator/KolWorkspacePage';

// ── 样本数据 ───────────────────────────────────────────────────────────────────
const sampleDashboard = {
  kol: { id: 1, name: '孙知羽', avatar_url: null, category: '美妆' },
  benchmarks: {
    content: [
      { id: 1, kol_id: 1, account_name: '内容对标A', account_type: 'content' as const, description: '对标描述', sort_order: 0 },
    ],
    livestream: [
      { id: 2, kol_id: 1, account_name: '直播对标B', account_type: 'livestream' as const, description: null, sort_order: 0 },
    ],
  },
  active_products: [
    {
      id: 10, nickname: '大红瓶精华', core_selling_point: '控油', visualization: null,
      mechanism: '双效控油', mechanism_exclusive: true, endorsement: null,
      user_feedback: null, unique_selling: null, awards: null, efficacy_proof: null,
      created_by: null, created_at: null, updated_at: null,
    },
  ],
};

const sampleProducts = {
  items: [
    {
      id: 10, nickname: '大红瓶精华', core_selling_point: '控油', visualization: null,
      mechanism: '双效控油', mechanism_exclusive: true, endorsement: null,
      user_feedback: null, unique_selling: null, awards: null, efficacy_proof: null,
      created_by: null, created_at: null, updated_at: null,
    },
    {
      id: 11, nickname: '美白面膜', core_selling_point: '美白', visualization: null,
      mechanism: null, mechanism_exclusive: false, endorsement: null,
      user_feedback: null, unique_selling: null, awards: null, efficacy_proof: null,
      created_by: null, created_at: null, updated_at: null,
    },
  ],
  pagination: { page: 1, page_size: 20, total: 2, total_pages: 1 },
};

// ── 工具函数 ───────────────────────────────────────────────────────────────────
function renderWorkspacePage(kolId = '1') {
  return render(
    <App>
      <MemoryRouter initialEntries={[`/kol-workspace/${kolId}`]}>
        <Routes>
          <Route path="/kol-workspace/:kol_id" element={<KolWorkspacePage />} />
          <Route path="/admin/kols" element={<div data-testid="kols-page">KolsPage</div>} />
        </Routes>
      </MemoryRouter>
    </App>
  );
}

// ── 测试 ───────────────────────────────────────────────────────────────────────
describe('KolWorkspacePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkspaceDashboard.mockResolvedValue(sampleDashboard);
    mockGetQianchuanProducts.mockResolvedValue(sampleProducts);
    mockCreateBenchmark.mockResolvedValue({ id: 99, kol_id: 1, account_name: '新账号', account_type: 'content', description: null, sort_order: 0 });
    mockUpdateActiveProducts.mockResolvedValue({ active_product_ids: [10] });
    mockGetPersonaDetails.mockResolvedValue({
      kol_id: 1, background: null, experience: null, relationships: null, unique_story: null, extra_notes: null, updated_at: null,
    });
    mockGetMaterialLibraryKolDetail.mockResolvedValue({
      id: 1, name: '孙知羽', account_name: null, category: null, follower_count: null, persona: '', content_plan: '',
      references: {
        '红人爆款文案': [], '红人喜欢的内容': [], '风格参考': [],
        '千川爆款文案': [], '千川喜欢的内容': [], '千川风格参考': [],
      },
    });
  });

  // Test 1: Shell 正常渲染（顶部栏显示、左侧导航显示）
  it('renders topbar and sidebar navigation', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('workspace-topbar')).toBeInTheDocument();
      expect(screen.getByTestId('workspace-sidebar')).toBeInTheDocument();
    });
    expect(screen.getByText('返回红人列表')).toBeInTheDocument();
    expect(screen.getByText('工作台首页')).toBeInTheDocument();
    expect(screen.getByText('产品库')).toBeInTheDocument();
    expect(screen.getByText('人物档案')).toBeInTheDocument();
  });

  it('uses workspace-specific shell classes for visual consistency', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('workspace-sidebar')).toBeInTheDocument();
    });
    expect(screen.getByTestId('workspace-sidebar')).toHaveClass('workspace-sidebar');
    expect(screen.getByTestId('nav-item-dashboard')).toHaveClass('workspace-nav-item');
    expect(screen.getByTestId('nav-item-dashboard')).toHaveClass('active');
  });

  // Test 2: 默认展示 Dashboard（activeTab='dashboard'）
  it('shows WorkspaceDashboard by default', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(mockGetWorkspaceDashboard).toHaveBeenCalledWith(1);
    });
    // Dashboard 加载后显示对标账号区
    await waitFor(() => {
      expect(screen.getByText('对标账号')).toBeInTheDocument();
    });
  });

  // Test 3: 点击产品库切换到 QianchuanProductsModule
  it('switches to QianchuanProductsModule when products tab is clicked', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-products')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('nav-item-products'));
    await waitFor(() => {
      expect(screen.getByText('千川产品库')).toBeInTheDocument();
    });
    expect(mockGetQianchuanProducts).toHaveBeenCalled();
  });

  it('opens the current kol material library from the workspace navigation', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();

    await user.click(await screen.findByTestId('nav-item-references'));
    expect(await screen.findByText('管理当前红人的六类脚本文档和视频原片')).toBeInTheDocument();
    expect(mockGetMaterialLibraryKolDetail).toHaveBeenCalledWith(1);
  });

  // Test 4: 禁用 Tab（千川成片预审 Sprint 23）点击后 activeTab 不变
  it('does not change activeTab when disabled nav item is clicked', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    // 等 dashboard 加载
    await waitFor(() => {
      expect(screen.getByText('对标账号')).toBeInTheDocument();
    });
    // 点击仍然禁用的千川成片预审（Sprint 23）
    await user.click(screen.getByTestId('nav-item-film-review'));
    // Dashboard 应仍然存在（activeTab 没变）
    await waitFor(() => {
      expect(screen.getByText('对标账号')).toBeInTheDocument();
    });
    // 千川产品库页不应出现
    expect(screen.queryByText('千川产品库')).not.toBeInTheDocument();
  });

  // Test 5: WorkspaceDashboard 对标账号正常展示（mock API 返回）
  it('shows benchmark accounts from dashboard API', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('内容对标A')).toBeInTheDocument();
      expect(screen.getByText('直播对标B')).toBeInTheDocument();
    });
  });

  // Test 6: WorkspaceDashboard 在售商品正常展示
  it('shows active products from dashboard API', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('大红瓶精华')).toBeInTheDocument();
    });
  });

  // Test 7: QianchuanProductsModule 列表展示
  it('shows product list in QianchuanProductsModule', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-products')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('nav-item-products'));
    await waitFor(() => {
      expect(screen.getByText('大红瓶精华')).toBeInTheDocument();
      expect(screen.getByText('美白面膜')).toBeInTheDocument();
    });
  });

  // Test 8: QianchuanProductsModule 新建弹窗表单校验（nickname 必填）
  it('shows validation error when nickname is empty in product form', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-products')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('nav-item-products'));
    await waitFor(() => {
      expect(screen.getByText('千川产品库')).toBeInTheDocument();
    });
    // 点击新建产品按钮（page-header 区域）
    const createBtns = screen.getAllByText('新建产品');
    await user.click(createBtns[0]);
    // Modal 应出现（等待 placeholder 出现）
    await waitFor(() => {
      expect(screen.getByPlaceholderText('请输入产品名称（用于区分识别）')).toBeInTheDocument();
    });
    // 直接触发表单 submit（模拟点击确定按钮）
    // AntD Modal 的 OK 按钮是 data-testid="modal-ok-button" 或用 fireEvent 直接提交表单
    const form = document.querySelector('.ant-modal-body form');
    if (form) fireEvent.submit(form);
    // 校验错误提示
    await waitFor(() => {
      expect(screen.getByText('请输入产品昵称')).toBeInTheDocument();
    });
  });

  // Test 9: API 错误时显示错误状态（非 crash）
  it('shows error state when dashboard API fails', async () => {
    mockGetWorkspaceDashboard.mockRejectedValue(new Error('网络错误'));
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('加载工作台数据失败')).toBeInTheDocument();
    });
    // 重试按钮存在
    expect(screen.getByText('重试')).toBeInTheDocument();
  });

  // Test 10: kol_id 无效时显示错误提示
  it('shows 404 message when kol_id is invalid', () => {
    render(
      <App>
        <MemoryRouter initialEntries={['/kol-workspace/abc']}>
          <Routes>
            <Route path="/kol-workspace/:kol_id" element={<KolWorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </App>
    );
    expect(screen.getByText('无效的红人 ID')).toBeInTheDocument();
  });

  // Test 11: 顶部栏显示红人姓名（从 dashboard 数据中读取）
  it('displays kol name in topbar after dashboard loads', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('孙知羽')).toBeInTheDocument();
    });
  });

  // Test 12: 对标账号弹窗 — 点击添加对标账号打开弹窗
  it('opens benchmark modal when add button is clicked', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('添加对标账号')).toBeInTheDocument();
    });
    await user.click(screen.getByText('添加对标账号'));
    await waitFor(() => {
      expect(screen.getByText('抖音账号')).toBeInTheDocument();
    });
  });

  // Test 13: Sprint 19 启用千川仿写 Tab — 点击后切换到 QianchuanWriterModule
  it('navigates to qianchuan-writer module when tab is clicked', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('对标账号')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('nav-item-qianchuan-writer'));
    // 千川仿写模块展示（加载产品卖点步骤出现）
    await waitFor(() => {
      expect(screen.getByText('千川文案写作')).toBeInTheDocument();
    });
  });

  it('uses compact workspace layout for writer modules', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-persona-writer')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('nav-item-persona-writer'));
    await waitFor(() => {
      expect(screen.getByText('人设脚本仿写')).toBeInTheDocument();
    });
    expect(document.querySelector('.workspace-tool-module')).toBeInTheDocument();

    await user.click(screen.getByTestId('nav-item-seeding-writer'));
    await waitFor(() => {
      expect(screen.getByText('种草内容仿写')).toBeInTheDocument();
    });
    expect(document.querySelector('.workspace-tool-module')).toBeInTheDocument();
  });

  it('uses padded step cards for writer modules', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-seeding-writer')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('nav-item-seeding-writer'));
    await waitFor(() => {
      expect(screen.getByText('种草内容仿写')).toBeInTheDocument();
    });
    expect(document.querySelector('.workspace-step-card')).toBeInTheDocument();

    await user.click(screen.getByTestId('nav-item-persona-writer'));
    await waitFor(() => {
      expect(screen.getByText('人设脚本仿写')).toBeInTheDocument();
    });
    expect(document.querySelector('.workspace-step-card')).toBeInTheDocument();
  });

  // Test 14: 点击「返回红人列表」导航到 /admin/kols
  it('navigates to /admin/kols when back button is clicked', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('返回红人列表')).toBeInTheDocument();
    });
    await user.click(screen.getByText('返回红人列表'));
    await waitFor(() => {
      expect(screen.getByTestId('kols-page')).toBeInTheDocument();
    });
  });
});

// ── WorkspaceDashboard 单独测试 ────────────────────────────────────────────────
describe('WorkspaceDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkspaceDashboard.mockResolvedValue(sampleDashboard);
    mockGetQianchuanProducts.mockResolvedValue(sampleProducts);
    mockUpdateActiveProducts.mockResolvedValue({ active_product_ids: [] });
  });

  // 产品「只有我有」标签展示
  it('shows mechanism_exclusive badge on product card', async () => {
    renderWorkspacePage();
    await waitFor(() => {
      expect(screen.getByText('只有我有')).toBeInTheDocument();
    });
  });

  it('keeps only the newly selected current product', async () => {
    const user = userEvent.setup();
    renderWorkspacePage();

    await user.click(await screen.findByRole('button', { name: '选择商品' }));
    await screen.findByText('美白面膜');
    await user.click(screen.getByText('美白面膜'));
    await user.click(screen.getByRole('button', { name: /保\s*存/ }));

    await waitFor(() => {
      expect(mockUpdateActiveProducts).toHaveBeenCalledWith(1, [11]);
    });
  });

  it('previews the current product when it is outside the loaded product page', async () => {
    const user = userEvent.setup();
    mockGetQianchuanProducts.mockResolvedValue({
      items: [sampleProducts.items[1]],
      pagination: { page: 1, page_size: 20, total: 2, total_pages: 1 },
    });

    renderWorkspacePage();
    await user.click(await screen.findByRole('button', { name: '选择商品' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('大红瓶精华')).toBeInTheDocument();
  });
});

// ── QianchuanProductsModule 单独测试 ──────────────────────────────────────────
describe('QianchuanProductsModule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetWorkspaceDashboard.mockResolvedValue(sampleDashboard);
    mockGetQianchuanProducts.mockResolvedValue(sampleProducts);
    mockCreateQianchuanProduct.mockResolvedValue({ ...sampleProducts.items[0], id: 99, nickname: '新产品' });
    mockUpdateQianchuanProduct.mockResolvedValue(sampleProducts.items[0]);
    mockDeleteQianchuanProduct.mockResolvedValue({ id: 10 });
  });

  function renderProductsModule() {
    return render(
      <App>
        <MemoryRouter initialEntries={['/kol-workspace/1']}>
          <Routes>
            <Route path="/kol-workspace/:kol_id" element={<KolWorkspacePage />} />
          </Routes>
        </MemoryRouter>
      </App>
    );
  }

  async function navigateToProducts() {
    const user = userEvent.setup();
    renderProductsModule();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-products')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('nav-item-products'));
    await waitFor(() => {
      expect(screen.getByText('千川产品库')).toBeInTheDocument();
    });
    return user;
  }

  it('shows product list with correct data', async () => {
    await navigateToProducts();
    await waitFor(() => {
      expect(screen.getByText('大红瓶精华')).toBeInTheDocument();
      expect(screen.getByText('美白面膜')).toBeInTheDocument();
    });
  });

  it('calls createQianchuanProduct when form is submitted with valid data', async () => {
    const user = await navigateToProducts();
    await waitFor(() => {
      expect(screen.getByText('千川产品库')).toBeInTheDocument();
    });
    // 点新建 - 使用页面操作按钮（page-actions 中的新建产品）
    const createBtns = screen.getAllByText('新建产品');
    await user.click(createBtns[0]);
    // 等待 Modal 出现（等待 placeholder 出现）
    await waitFor(() => {
      expect(screen.getByPlaceholderText('请输入产品名称（用于区分识别）')).toBeInTheDocument();
    });
    // 填写 nickname
    const nicknameInput = screen.getByPlaceholderText('请输入产品名称（用于区分识别）');
    await user.type(nicknameInput, '测试新产品');
    // 提交：直接触发 form submit
    const form = document.querySelector('.ant-modal-body form');
    if (form) fireEvent.submit(form);
    await waitFor(() => {
      expect(mockCreateQianchuanProduct).toHaveBeenCalledWith(
        expect.objectContaining({ nickname: '测试新产品' })
      );
    });
  });

  it('shows error state when products API fails', async () => {
    vi.clearAllMocks();
    mockGetWorkspaceDashboard.mockResolvedValue(sampleDashboard);
    mockGetQianchuanProducts.mockRejectedValue(new Error('服务器错误'));
    const user = userEvent.setup();
    renderProductsModule();
    await waitFor(() => {
      expect(screen.getByTestId('nav-item-products')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('nav-item-products'));
    // 不会 crash（loading state 后显示空状态或 error toast）
    await waitFor(() => {
      expect(screen.getByText('千川产品库')).toBeInTheDocument();
    });
  });
});
