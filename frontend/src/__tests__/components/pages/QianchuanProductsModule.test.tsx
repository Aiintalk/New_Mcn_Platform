import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from 'antd';

const mockGetProducts = vi.fn();

vi.mock('../../../api/qianchuanProducts', () => ({
  getQianchuanProducts: (...args: unknown[]) => mockGetProducts(...args),
  createQianchuanProduct: vi.fn(),
  updateQianchuanProduct: vi.fn(),
  deleteQianchuanProduct: vi.fn(),
}));

import QianchuanProductsModule from '../../../pages/operator/workspace/QianchuanProductsModule';

describe('QianchuanProductsModule', () => {
  beforeEach(() => {
    mockGetProducts.mockResolvedValue({
      items: [{
        id: 1,
        nickname: '完整商品卡验收商品',
        core_selling_point: '控油持妆 12 小时',
        visualization: '吸油纸前后对比',
        mechanism: '首发破价并买一赠一',
        mechanism_exclusive: true,
        endorsement: '皮肤科医生表姐推荐',
        user_feedback: '油皮用户反馈下午不斑驳',
        unique_selling: '独家持妆膜技术',
        awards: '2026 虚拟美妆榜单',
        efficacy_proof: '28 天持妆测试数据',
        created_by: 1,
        created_at: null,
        updated_at: null,
      }],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
    });
  });

  it('把商品所有非空字段作为可扫描卡片直接展示', async () => {
    render(<App><QianchuanProductsModule /></App>);

    expect(await screen.findByText('完整商品卡验收商品')).toBeInTheDocument();
    expect(screen.getByText('吸油纸前后对比')).toBeInTheDocument();
    expect(screen.getByText('首发破价并买一赠一')).toBeInTheDocument();
    expect(screen.getByText('皮肤科医生表姐推荐')).toBeInTheDocument();
    expect(screen.getByText('油皮用户反馈下午不斑驳')).toBeInTheDocument();
    expect(screen.getByText('独家持妆膜技术')).toBeInTheDocument();
    expect(screen.getByText('2026 虚拟美妆榜单')).toBeInTheDocument();
    expect(screen.getByText('28 天持妆测试数据')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.getByText('产品库')).toBeInTheDocument();
    expect(screen.getByText('所有脚本工具都会从这里读取产品信息')).toBeInTheDocument();
    expect(screen.getByTestId('product-card-1').querySelector('[style*="gridTemplateColumns"]')).toBeNull();
  });
});
