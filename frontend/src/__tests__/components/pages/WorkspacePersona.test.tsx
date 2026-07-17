import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from 'antd';
import { render, screen } from '@testing-library/react';

const mockGetPersonaDetails = vi.fn();

vi.mock('../../../api/kolWorkspace', () => ({
  getPersonaDetails: (...args: unknown[]) => mockGetPersonaDetails(...args),
  updatePersonaDetails: vi.fn(),
}));

import WorkspacePersona from '../../../pages/operator/workspace/WorkspacePersona';

describe('WorkspacePersona', () => {
  beforeEach(() => {
    mockGetPersonaDetails.mockResolvedValue({
      kol_id: 1,
      background: '【身份】\n- 美妆主播\n1. 曾做过柜姐\n⚠️ 不谈夸大功效',
      experience: '真实经历', relationships: '关系网', unique_story: '独家经历', extra_notes: '其他补充',
      updated_at: '2026-07-14T08:00:00Z',
    });
  });

  it('按文档式单列渲染五分区和文本层级', async () => {
    render(<App><WorkspacePersona kolId={1} kolName="测试红人" /></App>);

    expect(await screen.findByText('测试红人人物档案')).toBeInTheDocument();
    expect(screen.getByText(/脚本改编时 AI 参考此档案替换人物细节/)).toBeInTheDocument();
    expect(screen.getByText('【身份】')).toBeInTheDocument();
    expect(screen.getByText('美妆主播')).toBeInTheDocument();
    expect(screen.getByText(/1\. 曾做过柜姐/)).toBeInTheDocument();
    expect(screen.getByText('⚠️ 不谈夸大功效')).toBeInTheDocument();
    expect(screen.queryAllByText('基本身份')[0].closest('.card')).toBeNull();
  });
});
