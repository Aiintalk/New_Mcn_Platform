import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGenerateReport, mockSaveReport } = vi.hoisted(() => ({
  mockGenerateReport: vi.fn(),
  mockSaveReport: vi.fn(),
}));

vi.mock('../../../api/qianchuanReview', () => ({
  parseFile: vi.fn(),
  generateReport: mockGenerateReport,
  saveReport: mockSaveReport,
  getOutputs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

import QianchuanReviewPage from '../../../pages/operator/QianchuanReviewPage';

async function addScriptAndGenerate(user: ReturnType<typeof userEvent.setup>) {
  render(<QianchuanReviewPage />);
  await user.click(screen.getByText('或者手动粘贴文案'));
  await user.type(screen.getByPlaceholderText(/粘贴千川脚本文案/), '需要保留的脚本正文');
  await user.click(screen.getByRole('button', { name: '添加脚本' }));
  await user.click(screen.getByRole('button', { name: '下一步：上传投放数据' }));
  await user.click(screen.getByRole('button', { name: '跳过，直接生成报告' }));
}

describe('QianchuanReviewPage 流终态', () => {
  beforeEach(() => vi.clearAllMocks());

  it('失败事件保留脚本并显示任务编号和重试，不开放报告操作', async () => {
    const user = userEvent.setup();
    mockGenerateReport.mockResolvedValue(new Response(
      'event: content\ndata: {"text":"半段内容"}\n\nevent: failed\ndata: {"task_id":77,"code":"GENERATION_FAILED","message":"AI 生成失败，请重新生成"}\n\n',
      { status: 200, headers: { 'X-Task-Id': '77', 'Content-Type': 'text/event-stream' } },
    ));

    await addScriptAndGenerate(user);

    expect(await screen.findByRole('alert')).toHaveTextContent('AI 生成失败，请重新生成');
    expect(screen.getByRole('alert')).toHaveTextContent('任务编号：77');
    expect(screen.getByText(/1 条素材/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新生成' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存到产出中心' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '导出下载' })).not.toBeInTheDocument();
  });

  it('只有收到完成事件且报告非空时开放保存与导出', async () => {
    const user = userEvent.setup();
    mockGenerateReport.mockResolvedValue(new Response(
      'event: content\ndata: {"text":"完整复盘报告"}\n\nevent: complete\ndata: {"task_id":78}',
      { status: 200, headers: { 'X-Task-Id': '78', 'Content-Type': 'text/event-stream' } },
    ));

    await addScriptAndGenerate(user);

    expect(await screen.findByText('完整复盘报告')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存到产出中心' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '导出下载' })).toBeInTheDocument();
  });
});
