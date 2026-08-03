import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from 'antd';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockGetPersonaDetails = vi.fn();
const mockUpdatePersonaDetails = vi.fn();
const mockFillEmptyPersonaFacts = vi.fn();

vi.mock('../../../api/kolWorkspace', () => ({
  getPersonaDetails: (...args: unknown[]) => mockGetPersonaDetails(...args),
  updatePersonaDetails: (...args: unknown[]) => mockUpdatePersonaDetails(...args),
  fillEmptyPersonaFacts: (...args: unknown[]) => mockFillEmptyPersonaFacts(...args),
}));

import WorkspacePersona from '../../../pages/operator/workspace/WorkspacePersona';

const sixOfSeven = {
  kol_id: 1,
  persona: '克制、真实、有生活经验的朋友',
  content_plan: '围绕职场和轻熟龄穿搭创作',
  background: '32 岁，曾从事服装买手工作',
  experience: '从线下服装店离职后开始拍短视频',
  relationships: '母亲偶尔参与试穿',
  unique_story: '第一次直播只卖出两件衣服',
  extra_notes: '',
  filled_count: 6,
  total_count: 7,
  updated_at: '2026-08-03T06:30:00Z',
};

function renderPersona() {
  return render(<App><WorkspacePersona kolId={1} kolName="测试红人" /></App>);
}

describe('WorkspacePersona', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetPersonaDetails.mockResolvedValue(sixOfSeven);
    mockUpdatePersonaDetails.mockImplementation(async (_kolId: number, data: Record<string, string>) => ({
      ...sixOfSeven,
      ...data,
      filled_count: data.extra_notes ? 7 : sixOfSeven.filled_count,
    }));
    mockFillEmptyPersonaFacts.mockResolvedValue({
      kol_id: 1,
      report_id: 88,
      filled_fields: ['extra_notes'],
      preserved_fields: ['background', 'experience', 'relationships', 'unique_story'],
    });
  });

  it('按定位信息在前、人物事实在后的顺序展示七字段和 6/7 完整度', async () => {
    renderPersona();

    expect(await screen.findByText('测试红人人物档案')).toBeInTheDocument();
    expect(screen.getByText('档案完整度 6/7')).toBeInTheDocument();

    const document = screen.getByTestId('workspace-persona-document');
    const orderedText = document.textContent ?? '';
    const labels = ['人格档案', '内容规划', '基本身份', '真实经历', '关系网', '独家经历', '其他补充'];
    labels.forEach((label) => expect(screen.getByText(label)).toBeInTheDocument());
    labels.slice(1).forEach((label, index) => {
      expect(orderedText.indexOf(labels[index])).toBeLessThan(orderedText.indexOf(label));
    });

    expect(screen.getAllByText('已填写')).toHaveLength(6);
    expect(screen.getByText('待补充')).toBeInTheDocument();
  });

  it('每次只打开一个字段编辑器，并支持取消和清空后单字段保存', async () => {
    const user = userEvent.setup();
    renderPersona();
    await screen.findByText('测试红人人物档案');

    await user.click(within(screen.getByTestId('persona-field-persona')).getByRole('button', { name: '编辑' }));
    expect(screen.getAllByRole('textbox')).toHaveLength(1);

    await user.click(within(screen.getByTestId('persona-field-content_plan')).getByRole('button', { name: '编辑' }));
    expect(screen.getAllByRole('textbox')).toHaveLength(1);
    expect(screen.getByRole('textbox')).toHaveValue(sixOfSeven.content_plan);

    await user.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();

    await user.click(within(screen.getByTestId('persona-field-persona')).getByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: '保存' }));

    await waitFor(() => {
      expect(mockUpdatePersonaDetails).toHaveBeenCalledWith(1, { persona: '' });
    });
  });

  it('补空只调用一次接口，并按返回字段反馈后刷新七字段', async () => {
    const user = userEvent.setup();
    mockGetPersonaDetails
      .mockResolvedValueOnce(sixOfSeven)
      .mockResolvedValueOnce({ ...sixOfSeven, extra_notes: '不制造焦虑', filled_count: 7 });
    renderPersona();

    await user.click(await screen.findByRole('button', { name: '从最新人格报告补全空字段' }));

    await waitFor(() => expect(mockFillEmptyPersonaFacts).toHaveBeenCalledTimes(1));
    expect(mockFillEmptyPersonaFacts).toHaveBeenCalledWith(1);
    expect(await screen.findByText(/已补全：其他补充/)).toBeInTheDocument();
    expect(screen.getByText(/已保留：基本身份、真实经历、关系网、独家经历/)).toBeInTheDocument();
    await waitFor(() => expect(mockGetPersonaDetails).toHaveBeenCalledTimes(2));
  });

  it('1024 宽度下使用可收缩容器，字段行没有超出容器的固定宽度', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 });
    window.dispatchEvent(new Event('resize'));
    renderPersona();

    const document = await screen.findByTestId('workspace-persona-document');
    expect(document).toHaveStyle({ width: '100%', maxWidth: '100%', minWidth: 0 });
    screen.getAllByTestId(/^persona-field-/).forEach((row) => {
      expect(row.style.width).not.toMatch(/\d+px/);
      expect(row).toHaveStyle({ minWidth: 0 });
    });
  });
});
