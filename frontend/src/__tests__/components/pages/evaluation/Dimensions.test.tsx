/**
 * Dimensions 页面测试（admin）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockListDimensions = vi.fn();
const mockListRubrics = vi.fn();
const mockUpdateDimension = vi.fn();
const mockReplaceRubrics = vi.fn();
const mockCreateDimension = vi.fn();
const mockDeleteDimension = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  listDimensions: (...args: unknown[]) => mockListDimensions(...args),
  listRubrics: (...args: unknown[]) => mockListRubrics(...args),
  updateDimension: (...args: unknown[]) => mockUpdateDimension(...args),
  replaceRubrics: (...args: unknown[]) => mockReplaceRubrics(...args),
  createDimension: (...args: unknown[]) => mockCreateDimension(...args),
  deleteDimension: (...args: unknown[]) => mockDeleteDimension(...args),
}));

import DimensionsPage from '../../../../evaluation/pages/Dimensions';

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

const sampleDimensions = [
  {
    id: 1,
    tool_code: 'qianchuan-writer',
    name: 'copy_quality',
    display_name: '文案质量',
    description: '钩子吸引力、叙事流畅度、信息密度',
    default_weight: 0.4,
    score_min: 1,
    score_max: 10,
    prompt_template: '你是千川脚本文案评审专家...',
    is_active: true,
    created_at: null,
    updated_at: null,
    deleted_at: null,
  },
  {
    id: 2,
    tool_code: 'qianchuan-writer',
    name: 'conversion_power',
    display_name: '种草力',
    description: null,
    default_weight: 0.35,
    score_min: 1,
    score_max: 10,
    prompt_template: '...',
    is_active: true,
    created_at: null,
    updated_at: null,
    deleted_at: null,
  },
];

const sampleRubrics = [
  { id: 1, dimension_id: 1, level: 10, criteria: '钩子极强，叙事流畅', scenario_tag: 'default', is_active: true, created_at: null, updated_at: null },
  { id: 2, dimension_id: 1, level: 8, criteria: '钩子较抓人', scenario_tag: 'default', is_active: true, created_at: null, updated_at: null },
  { id: 3, dimension_id: 1, level: 6, criteria: '有钩子但力度一般', scenario_tag: 'default', is_active: true, created_at: null, updated_at: null },
];

describe('DimensionsPage', () => {
  beforeEach(() => {
    mockListDimensions.mockReset();
    mockListRubrics.mockReset();
    mockUpdateDimension.mockReset();
    mockReplaceRubrics.mockReset();
    mockCreateDimension.mockReset();
    mockDeleteDimension.mockReset();
  });

  it('渲染维度列表与默认选中第一个维度', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    renderWithProviders(<DimensionsPage />);
    expect(screen.getByText('维度与评分标准')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('文案质量')).toBeInTheDocument();
      expect(screen.getByText('种草力')).toBeInTheDocument();
    });
    // 默认选中第一个 → 触发 rubric 加载
    expect(mockListRubrics).toHaveBeenCalledWith(1);
  });

  it('加载失败时显示错误', async () => {
    mockListDimensions.mockRejectedValue(new Error('权限拒绝'));
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => {
      expect(screen.getByText('权限拒绝')).toBeInTheDocument();
    });
  });

  it('空维度列表显示空状态', async () => {
    mockListDimensions.mockResolvedValue([]);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => {
      expect(screen.getByText('暂无维度，点击右上角「新建维度」开始')).toBeInTheDocument();
    });
  });
});

describe('DimensionsPage — 维度与 Rubric 交互', () => {
  beforeEach(() => {
    mockListDimensions.mockReset();
    mockListRubrics.mockReset();
    mockUpdateDimension.mockReset();
    mockReplaceRubrics.mockReset();
    mockCreateDimension.mockReset();
    mockDeleteDimension.mockReset();
  });

  async function renderLoaded() {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => expect(screen.getByText('文案质量')).toBeInTheDocument());
  }

  it('保存维度配置调用 updateDimension', async () => {
    await renderLoaded();
    mockUpdateDimension.mockResolvedValue({});
    fireEvent.click(screen.getByText('保存配置'));
    await waitFor(() => {
      expect(mockUpdateDimension).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ name: 'copy_quality', display_name: '文案质量' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/维度配置已保存/)).toBeInTheDocument();
    });
  });

  it('保存全部修改调用 replaceRubrics（整批 3 条）', async () => {
    await renderLoaded();
    mockReplaceRubrics.mockResolvedValue([]);
    fireEvent.click(screen.getByText('保存全部修改'));
    await waitFor(() => {
      expect(mockReplaceRubrics).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ rubrics: expect.any(Array) }),
      );
      expect(mockReplaceRubrics.mock.calls[0][1].rubrics.length).toBe(3);
    });
    await waitFor(() => {
      expect(screen.getByText(/Rubric 已保存/)).toBeInTheDocument();
    });
  });

  it('添加等级后再保存，replaceRubrics 含 4 条', async () => {
    await renderLoaded();
    mockReplaceRubrics.mockResolvedValue([]);
    fireEvent.click(screen.getByText('添加等级'));
    fireEvent.click(screen.getByText('保存全部修改'));
    await waitFor(() => {
      expect(mockReplaceRubrics.mock.calls[0][1].rubrics.length).toBe(4);
    });
  });

  it('保存维度配置失败时提示错误', async () => {
    await renderLoaded();
    mockUpdateDimension.mockRejectedValue(new Error('校验失败'));
    fireEvent.click(screen.getByText('保存配置'));
    await waitFor(() => {
      expect(screen.getByText(/校验失败/)).toBeInTheDocument();
    });
  });

  it('新建维度：填必填项后创建调用 createDimension', async () => {
    await renderLoaded();
    fireEvent.click(screen.getByText('新建维度'));
    const nameInput = await screen.findByPlaceholderText('例：copy_quality');
    fireEvent.change(nameInput, { target: { value: 'persona_fit' } });
    fireEvent.change(screen.getByPlaceholderText('例：文案质量'), { target: { value: '人设一致性' } });
    mockCreateDimension.mockResolvedValue({});
    // Modal okText="创建"（2 字 → "创 建"）
    fireEvent.click(screen.getByText(/创\s*建/));
    await waitFor(() => {
      expect(mockCreateDimension).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'persona_fit', display_name: '人设一致性', tool_code: 'qianchuan-writer' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText(/维度已创建/)).toBeInTheDocument();
    });
  });

  it('删除维度：确认后调用 deleteDimension', async () => {
    await renderLoaded();
    mockDeleteDimension.mockResolvedValue({});
    // 维度行与 rubric 行都有「删除」按钮，用 within 限定到维度行（display_name 文案质量）
    const dimRow = screen.getByText('文案质量').closest('tr')!;
    fireEvent.click(within(dimRow).getByText(/删\s*除/));
    // 确认弹窗 okText="软删"（2 字 → "软 删"）；title 也含「软删」，用 role=button 精确命中按钮
    const confirmBtn = await screen.findByRole('button', { name: /软\s*删/ });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(mockDeleteDimension).toHaveBeenCalledWith(1);
    });
  });
});

describe('DimensionsPage — 边界与错误路径', () => {
  beforeEach(() => {
    mockListDimensions.mockReset();
    mockListRubrics.mockReset();
    mockUpdateDimension.mockReset();
    mockReplaceRubrics.mockReset();
    mockCreateDimension.mockReset();
    mockDeleteDimension.mockReset();
  });

  it('停用维度渲染 off 标签（覆盖 is_active=false 分支）', async () => {
    mockListDimensions.mockResolvedValue([{ ...sampleDimensions[0], is_active: false }]);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => {
      expect(screen.getByText('off')).toBeInTheDocument();
    });
  });

  it('Rubric 无 default 场景时取第一个 scenario（覆盖分支 117）', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue([
      { id: 1, dimension_id: 1, level: 10, criteria: '护肤场景高分', scenario_tag: 'skincare', is_active: true, created_at: null, updated_at: null },
    ]);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => {
      expect(screen.getByText('护肤场景高分')).toBeInTheDocument();
    });
  });

  it('Rubric 加载失败时提示错误', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockRejectedValue(new Error('Rubric 拉取失败'));
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Rubric 拉取失败/)).toBeInTheDocument();
    });
  });

  it('保存全部修改失败时提示错误', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => expect(screen.getByText('文案质量')).toBeInTheDocument());
    mockReplaceRubrics.mockRejectedValue(new Error('Rubric 保存失败'));
    fireEvent.click(screen.getByText('保存全部修改'));
    await waitFor(() => {
      expect(screen.getByText(/Rubric 保存失败/)).toBeInTheDocument();
    });
  });

  it('新建维度失败时提示错误', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => expect(screen.getByText('文案质量')).toBeInTheDocument());
    fireEvent.click(screen.getByText('新建维度'));
    const nameInput = await screen.findByPlaceholderText('例：copy_quality');
    fireEvent.change(nameInput, { target: { value: 'dup_name' } });
    fireEvent.change(screen.getByPlaceholderText('例：文案质量'), { target: { value: '重名' } });
    mockCreateDimension.mockRejectedValue(new Error('英文名已存在'));
    fireEvent.click(screen.getByText(/创\s*建/));
    await waitFor(() => {
      expect(screen.getByText(/英文名已存在/)).toBeInTheDocument();
    });
  });

  it('删除维度失败时提示错误', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => expect(screen.getByText('文案质量')).toBeInTheDocument());
    mockDeleteDimension.mockRejectedValue(new Error('删除失败XYZ'));
    const row = screen.getByText('文案质量').closest('tr')!;
    fireEvent.click(within(row).getByText(/删\s*除/));
    const confirmBtn = await screen.findByRole('button', { name: /软\s*删/ });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(screen.getByText(/删除失败XYZ/)).toBeInTheDocument();
    });
  });

  it('编辑 rubric criteria 后保存（覆盖 handleUpdateDraft）', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    mockReplaceRubrics.mockResolvedValue([]);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => expect(screen.getByText('文案质量')).toBeInTheDocument());
    const criteriaInputs = screen.getAllByPlaceholderText(/开头 3 秒钩子极强/);
    fireEvent.change(criteriaInputs[0], { target: { value: '改后的标准描述' } });
    fireEvent.click(screen.getByText('保存全部修改'));
    await waitFor(() => {
      expect(mockReplaceRubrics.mock.calls[0][1].rubrics[0].criteria).toBe('改后的标准描述');
    });
  });

  it('删除一条 rubric draft 后保存（覆盖 handleRemoveDraft）', async () => {
    mockListDimensions.mockResolvedValue(sampleDimensions);
    mockListRubrics.mockResolvedValue(sampleRubrics);
    mockReplaceRubrics.mockResolvedValue([]);
    renderWithProviders(<DimensionsPage />);
    await waitFor(() => expect(screen.getByText('文案质量')).toBeInTheDocument());
    const criteriaInputs = screen.getAllByPlaceholderText(/开头 3 秒钩子极强/);
    const rubricRow = criteriaInputs[0].closest('tr')!;
    fireEvent.click(within(rubricRow).getByText(/删\s*除/));
    fireEvent.click(screen.getByText('保存全部修改'));
    await waitFor(() => {
      expect(mockReplaceRubrics.mock.calls[0][1].rubrics.length).toBe(2);
    });
  });
});
