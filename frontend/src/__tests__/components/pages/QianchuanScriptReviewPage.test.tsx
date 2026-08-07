import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

// ── Mock API ──────────────────────────────────────────────────────────────────

const mockSubmitReview = vi.fn();
const mockSaveOutput = vi.fn();
const mockGetQianchuanProducts = vi.fn();

vi.mock('../../../api/scriptReview', () => ({
  submitReview: (...args: unknown[]) => mockSubmitReview(...args),
  saveOutput: (...args: unknown[]) => mockSaveOutput(...args),
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
      task_id: 101,
      rating: 'pass',
      must_fix: [],
      suggestions: [],
      passed: ['结构完整', '卖点清晰'],
    });
  });

  it('审核失败后持续显示原因、保留输入并允许原地重试', async () => {
    const user = userEvent.setup();
    mockSubmitReview
      .mockRejectedValueOnce(new Error('AI 返回的审核结果结构不完整，请重新审核'))
      .mockResolvedValueOnce({ task_id: 102, rating: 'pass', must_fix: [], suggestions: [], passed: [] });
    renderModule();

    const original = screen.getByPlaceholderText('粘贴原版千川脚本...');
    const adapted = screen.getByPlaceholderText('粘贴待审核的仿写脚本...');
    await user.type(original, '保留的原版脚本');
    await user.type(adapted, '保留的仿写脚本');
    await user.click(screen.getByRole('button', { name: /开始预审/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('AI 返回的审核结果结构不完整，请重新审核');
    expect(original).toHaveValue('保留的原版脚本');
    expect(adapted).toHaveValue('保留的仿写脚本');
    expect(screen.queryByRole('button', { name: '保存到历史' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '重新审核' }));
    expect(await screen.findByText('✅ 通过，可以上线')).toBeInTheDocument();
    expect(mockSubmitReview).toHaveBeenCalledTimes(2);
  });

  it('前端拒绝结构不完整的成功响应且不开放保存', async () => {
    const user = userEvent.setup();
    mockSubmitReview.mockResolvedValue({ task_id: 103, rating: 'unknown', must_fix: 'bad' });
    renderModule();
    await user.type(screen.getByPlaceholderText('粘贴原版千川脚本...'), '原版');
    await user.type(screen.getByPlaceholderText('粘贴待审核的仿写脚本...'), '仿写');
    await user.click(screen.getByRole('button', { name: /开始预审/ }));

    expect(await screen.findByRole('alert')).toHaveTextContent('审核结果结构异常，请重新审核');
    expect(screen.queryByRole('button', { name: '保存到历史' })).not.toBeInTheDocument();
  });

  it('审核成功后编辑输入会失效旧任务结果并关闭保存门禁', async () => {
    const user = userEvent.setup();
    renderModule();
    const original = screen.getByPlaceholderText('粘贴原版千川脚本...');
    const adapted = screen.getByPlaceholderText('粘贴待审核的仿写脚本...');
    await user.type(original, '原版');
    await user.type(adapted, '仿写');
    await user.click(screen.getByRole('button', { name: /开始预审/ }));

    expect(await screen.findByRole('button', { name: '保存到历史' })).toBeInTheDocument();
    await user.type(adapted, '新增内容');
    expect(screen.queryByRole('button', { name: '保存到历史' })).not.toBeInTheDocument();
  });

  it('审核中修改输入后忽略旧请求的迟到失败', async () => {
    const user = userEvent.setup();
    let rejectReview!: (reason?: unknown) => void;
    mockSubmitReview.mockReturnValueOnce(new Promise((_, reject) => { rejectReview = reject; }));
    renderModule();
    const original = screen.getByPlaceholderText('粘贴原版千川脚本...');
    const adapted = screen.getByPlaceholderText('粘贴待审核的仿写脚本...');
    await user.type(original, '原版');
    await user.type(adapted, '仿写');
    await user.click(screen.getByRole('button', { name: /开始预审/ }));
    await waitFor(() => expect(mockSubmitReview).toHaveBeenCalledTimes(1));

    await user.type(adapted, '新输入');
    await act(async () => rejectReview(new Error('旧请求失败')));

    await waitFor(() => expect(screen.getByRole('button', { name: /开始预审/ })).not.toBeDisabled());
    expect(adapted).toHaveValue('仿写新输入');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText('旧请求失败')).not.toBeInTheDocument();
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
      task_id: 104,
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
      task_id: 105,
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

    // 等按钮变为 enabled（canSubmit = true）再点击
    const submitBtn = await screen.findByRole('button', { name: /开始预审/ });
    await waitFor(() => expect(submitBtn).not.toBeDisabled());
    await user.click(submitBtn);

    // 等待结果
    await waitFor(() => {
      expect(screen.getByText('❌ 需要大改')).toBeInTheDocument();
    });

    // must_fix 列表展示
    expect(screen.getByText('❌ 必须修改（2 条）')).toBeInTheDocument();
    expect(screen.getByText(/最好的产品/)).toBeInTheDocument();
    expect(screen.getByText(/删除绝对化用语/)).toBeInTheDocument();
    expect(screen.getByText(/效果好/)).toBeInTheDocument();
    expect(screen.getByText(/补充具体数据支撑/)).toBeInTheDocument();

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
      task_id: 106,
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
