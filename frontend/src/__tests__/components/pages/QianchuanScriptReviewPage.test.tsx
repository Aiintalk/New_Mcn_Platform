import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// ── Mock API ──────────────────────────────────────────────────────────────────

const mockSubmitReview = vi.fn();
const mockGetQianchuanProducts = vi.fn();

vi.mock('../../../api/scriptReview', () => ({
  submitReview: (...args: unknown[]) => mockSubmitReview(...args),
  getConfig: vi.fn().mockResolvedValue({
    id: 1,
    config_key: 'default',
    direct_prompt: null,
    value_prompt: null,
    ai_model_id: null,
    is_active: true,
    updated_at: null,
  }),
  updateConfig: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../api/qianchuanProducts', () => ({
  getQianchuanProducts: (...args: unknown[]) => mockGetQianchuanProducts(...args),
}));

vi.mock('../../../api/request', () => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  put: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: { getState: () => ({ token: 'mock-token' }) },
}));

// ── 渲染 helper ───────────────────────────────────────────────────────────────

import { QianchuanScriptReviewModule } from '../../../pages/operator/QianchuanScriptReviewPage';

const sampleProducts = {
  items: [
    {
      id: 1,
      nickname: '大红瓶精华',
      core_selling_point: '控油',
      visualization: null,
      mechanism: '双效控油',
      mechanism_exclusive: true,
      endorsement: null,
      user_feedback: null,
      unique_selling: null,
      awards: null,
      efficacy_proof: null,
      created_by: null,
      created_at: null,
      updated_at: null,
    },
  ],
  pagination: { page: 1, page_size: 100, total: 1, total_pages: 1 },
};

function renderModule() {
  return render(
    <App>
      <QianchuanScriptReviewModule />
    </App>,
  );
}

// ── 测试 ───────────────────────────────────────────────────────────────────────

describe('QianchuanScriptReviewPage — QianchuanScriptReviewModule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetQianchuanProducts.mockResolvedValue(sampleProducts);
    mockSubmitReview.mockResolvedValue({
      rating: 'pass',
      must_fix: [],
      suggestions: [],
      passed: ['结构完整', '卖点清晰'],
    });
  });

  // Test 1: 页面渲染 — 两个 TextArea、脚本类型切换按钮
  it('渲染两个脚本输入区和类型切换按钮', async () => {
    renderModule();

    // 两个 textarea 都存在（原版脚本和仿写脚本）
    const textareas = screen.getAllByRole('textbox');
    expect(textareas.length).toBeGreaterThanOrEqual(2);

    // 脚本类型切换按钮
    expect(screen.getByRole('button', { name: '千川直销' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '价值观内容' })).toBeInTheDocument();

    // 页面标题
    expect(screen.getByText('千川脚本预审')).toBeInTheDocument();
  });

  // Test 2: 类型切换 — 点「价值观内容」→ 产品选择区隐藏
  it('切换为价值观内容类型后产品选择区隐藏', async () => {
    const user = userEvent.setup();
    renderModule();

    // 默认 direct 模式：产品选择区存在
    await waitFor(() => {
      expect(screen.getByText('关联产品（可选）：')).toBeInTheDocument();
    });

    // 切换为价值观模式
    await user.click(screen.getByRole('button', { name: '价值观内容' }));

    // 产品选择区应消失
    await waitFor(() => {
      expect(screen.queryByText('关联产品（可选）：')).not.toBeInTheDocument();
    });
  });

  // Test 3: 提交审核 — mock pass → 渲染绿色 Banner
  it('提交审核并返回 pass 评级时渲染绿色 Banner', async () => {
    const user = userEvent.setup();
    mockSubmitReview.mockResolvedValue({
      rating: 'pass',
      must_fix: [],
      suggestions: [],
      passed: ['结构完整', '卖点清晰'],
    });

    renderModule();

    // 用 placeholder 精确定位两个 textarea（避免 AntD Select 的 input 干扰）
    const originalTextarea = screen.getByPlaceholderText('粘贴原版千川脚本...');
    const adaptedTextarea = screen.getByPlaceholderText('粘贴待审核的仿写脚本...');
    await user.click(originalTextarea);
    await user.type(originalTextarea, '这是原版脚本内容');
    await user.click(adaptedTextarea);
    await user.type(adaptedTextarea, '这是仿写脚本内容');

    // 点击开始预审
    const submitBtn = screen.getByRole('button', { name: /开始预审/ });
    await user.click(submitBtn);

    // 等待结果出现
    await waitFor(() => {
      expect(screen.getByText('✅ 通过，可以上线')).toBeInTheDocument();
    });

    // 验证已通过 Tag 展示
    expect(screen.getByText('结构完整')).toBeInTheDocument();
    expect(screen.getByText('卖点清晰')).toBeInTheDocument();

    // 验证 submitReview 被正确调用
    expect(mockSubmitReview).toHaveBeenCalledWith(
      expect.objectContaining({
        script_type: 'direct',
        original_script: '这是原版脚本内容',
        adapted_script: '这是仿写脚本内容',
      }),
    );
  });

  // Test 4: 提交审核 — mock fail + must_fix → 红色 Banner + must_fix 列表
  it('提交审核并返回 fail 评级时渲染红色 Banner 和 must_fix 列表', async () => {
    const user = userEvent.setup();
    mockSubmitReview.mockResolvedValue({
      rating: 'fail',
      must_fix: [
        { type: '违规词', quote: '最好的产品', fix: '删除绝对化用语' },
        { type: '卖点缺失', quote: '效果好', fix: '补充具体数据支撑' },
      ],
      suggestions: ['可以增加用户故事'],
      passed: [],
    });

    renderModule();

    // 用 placeholder 精确定位 textarea
    const originalTextarea = screen.getByPlaceholderText('粘贴原版千川脚本...');
    const adaptedTextarea = screen.getByPlaceholderText('粘贴待审核的仿写脚本...');
    await user.click(originalTextarea);
    await user.type(originalTextarea, '原版脚本');
    await user.click(adaptedTextarea);
    await user.type(adaptedTextarea, '仿写脚本');

    // 点击开始预审
    const submitBtn = screen.getByRole('button', { name: /开始预审/ });
    await user.click(submitBtn);

    // 等待结果
    await waitFor(() => {
      expect(screen.getByText('❌ 需要大改')).toBeInTheDocument();
    });

    // must_fix 列表展示
    expect(screen.getByText('❌ 必须修改（2 条）')).toBeInTheDocument();
    expect(screen.getByText('最好的产品')).toBeInTheDocument();
    expect(screen.getByText('删除绝对化用语')).toBeInTheDocument();
    expect(screen.getByText('效果好')).toBeInTheDocument();
    expect(screen.getByText('补充具体数据支撑')).toBeInTheDocument();

    // 建议优化
    expect(screen.getByText('⚠️ 建议优化')).toBeInTheDocument();
    expect(screen.getByText('可以增加用户故事')).toBeInTheDocument();
  });

  // Test 5: 按钮禁用 — 两个 TextArea 未填时「开始预审」按钮禁用
  it('两个 TextArea 未填时开始预审按钮禁用', async () => {
    renderModule();

    const submitBtn = screen.getByRole('button', { name: /开始预审/ });

    // 初始状态：两个都未填 → disabled
    expect(submitBtn).toBeDisabled();
  });

  // 补充：只填一个 TextArea 时按钮仍禁用
  it('只填原版脚本时开始预审按钮仍禁用', async () => {
    const user = userEvent.setup();
    renderModule();

    const originalTextarea = screen.getByPlaceholderText('粘贴原版千川脚本...');
    await user.click(originalTextarea);
    await user.type(originalTextarea, '原版脚本内容');

    const submitBtn = screen.getByRole('button', { name: /开始预审/ });
    expect(submitBtn).toBeDisabled();
  });

  // 补充：minor 评级 Banner
  it('提交审核返回 minor 评级时渲染黄色 Banner', async () => {
    const user = userEvent.setup();
    mockSubmitReview.mockResolvedValue({
      rating: 'minor',
      must_fix: [],
      suggestions: ['建议优化开头节奏'],
      passed: ['卖点完整'],
    });

    renderModule();

    const originalTextarea = screen.getByPlaceholderText('粘贴原版千川脚本...');
    const adaptedTextarea = screen.getByPlaceholderText('粘贴待审核的仿写脚本...');
    await user.click(originalTextarea);
    await user.type(originalTextarea, '原版脚本');
    await user.click(adaptedTextarea);
    await user.type(adaptedTextarea, '仿写脚本');

    await act(async () => {
      screen.getByRole('button', { name: /开始预审/ }).click();
    });

    await waitFor(() => {
      expect(screen.getByText('⚠️ 小改可上线')).toBeInTheDocument();
    });
  });
});
