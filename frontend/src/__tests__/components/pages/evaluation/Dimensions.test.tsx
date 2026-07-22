/**
 * Dimensions 页面测试（admin）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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
