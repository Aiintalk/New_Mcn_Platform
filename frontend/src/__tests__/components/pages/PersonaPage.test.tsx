import { App } from 'antd';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, message: { success: vi.fn(), error: vi.fn() } };
});

const {
  mockGetPersonaKols,
  mockGetPersonaKolIntake,
  mockParseFile,
  mockGeneratePersona,
  mockGetPersonaReportDetail,
  mockSyncPersonaReportDecisions,
} = vi.hoisted(() => ({
  mockGetPersonaKols: vi.fn(),
  mockGetPersonaKolIntake: vi.fn(),
  mockParseFile: vi.fn(),
  mockGeneratePersona: vi.fn(),
  mockGetPersonaReportDetail: vi.fn(),
  mockSyncPersonaReportDecisions: vi.fn(),
}));

vi.mock('../../../api/persona', () => ({
  fetchDouyin: vi.fn(),
  parseFile: mockParseFile,
  downloadQuestionnaireTemplate: vi.fn(),
  generatePersona: mockGeneratePersona,
  optimizePersona: vi.fn(),
  exportPersonaWord: vi.fn(),
  getKolSubmissions: vi.fn().mockResolvedValue([]),
  getPersonaKols: mockGetPersonaKols,
  getPersonaKolIntake: mockGetPersonaKolIntake,
  getPersonaReports: vi.fn().mockResolvedValue([]),
  getPersonaReportDetail: mockGetPersonaReportDetail,
  syncPersonaReportDecisions: mockSyncPersonaReportDecisions,
  deletePersonaReport: vi.fn(),
}));

import PersonaPage from '../../../pages/operator/PersonaPage';

const formalKols = {
  items: [
    {
      id: 43,
      name: 'mini兔兔',
      account_name: '兔兔日常',
      douyin_id: 'mini2026',
      profile_filled_count: 6,
      profile_total: 7,
    },
    {
      id: 56,
      name: '韩国欧尼慧敏',
      account_name: '慧敏在首尔',
      douyin_id: 'huimin56',
      profile_filled_count: 7,
      profile_total: 7,
    },
  ],
  pagination: { page: 1, page_size: 20, total: 2, total_pages: 1 },
};

function renderPage() {
  return render(<App><PersonaPage /></App>);
}

function doneReader() {
  return {
    read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
  } as unknown as ReadableStreamDefaultReader<Uint8Array>;
}

async function selectKolAndUpload(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: /mini兔兔.*兔兔日常.*6\/7/ });
  await user.selectOptions(screen.getByLabelText('目标达人（必填）'), '43');
  await waitFor(() => expect(mockGetPersonaKolIntake).toHaveBeenCalledWith(43));
  const file = new File(['访谈正文'], 'manual.txt', { type: 'text/plain' });
  await user.upload(screen.getByLabelText('上传达人资料'), file);
  await screen.findByText('manual.txt');
}

describe('PersonaPage 正式达人绑定', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetPersonaKols.mockResolvedValue(formalKols);
    mockGetPersonaKolIntake.mockResolvedValue(null);
    mockParseFile.mockResolvedValue({ text: '手工上传的访谈正文' });
    mockGeneratePersona.mockResolvedValue({ reader: doneReader(), reportId: 88 });
    mockGetPersonaReportDetail.mockResolvedValue({
      id: 88,
      kol_id: 43,
      influencer_name: 'mini兔兔',
      douyin_nickname: null,
      douyin_id: null,
      status: 'ready',
      profile_result: '新人格档案',
      plan_result: '新内容规划',
      raw_output: '新人格档案===SPLIT===新内容规划',
      created_at: '2026-08-03T10:00:00+08:00',
      generated_at: '2026-08-03T10:01:00+08:00',
      sync_result: {},
      pending_overwrites: [],
    });
    mockSyncPersonaReportDecisions.mockResolvedValue({});
  });

  it('达人列表失败可见可重试，并保留已经输入的补充信息', async () => {
    const user = userEvent.setup();
    mockGetPersonaKols
      .mockRejectedValueOnce(new Error('网络错误'))
      .mockResolvedValueOnce(formalKols);
    renderPage();

    await user.type(screen.getByPlaceholderText('输入补充说明...'), '不要丢失这段输入');
    expect(await screen.findByText('达人列表加载失败，请重试')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试加载达人' }));

    await screen.findByRole('option', { name: /mini兔兔/ });
    expect(screen.getByPlaceholderText('输入补充说明...')).toHaveValue('不要丢失这段输入');
    expect(mockGetPersonaKols).toHaveBeenCalledTimes(2);
  });

  it('按关键词搜索正式达人，展示账号和完整度，且选择达人本身不能满足材料门槛', async () => {
    const user = userEvent.setup();
    renderPage();

    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
    expect(mockGetPersonaKolIntake).not.toHaveBeenCalled();
    await user.type(screen.getByPlaceholderText('搜索达人名称、账号或抖音号'), '兔兔');
    await waitFor(() => expect(mockGetPersonaKols).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      keyword: '兔兔',
    }));
    const option = await screen.findByRole('option', { name: /mini兔兔.*兔兔日常.*mini2026.*6\/7/ });
    expect(option).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('目标达人（必填）'), '43');
    await waitFor(() => expect(mockGetPersonaKolIntake).toHaveBeenCalledWith(43));
    expect(screen.getByRole('button', { name: '下一步' })).toBeDisabled();
  });

  it('连续输入搜索词时丢弃较早关键词的迟到列表响应', async () => {
    const user = userEvent.setup();
    let resolveEarly: ((value: typeof formalKols) => void) | undefined;
    let resolveLatest: ((value: typeof formalKols) => void) | undefined;
    mockGetPersonaKols.mockImplementation(({ keyword }: { keyword?: string }) => {
      if (!keyword) return Promise.resolve(formalKols);
      return new Promise(resolve => {
        if (keyword === '兔') resolveEarly = resolve;
        if (keyword === '兔兔') resolveLatest = resolve;
      });
    });
    renderPage();
    await screen.findByRole('option', { name: /mini兔兔/ });
    await user.type(screen.getByPlaceholderText('搜索达人名称、账号或抖音号'), '兔兔');

    await act(async () => resolveLatest?.({ ...formalKols, items: [formalKols.items[0]] }));
    expect(await screen.findByRole('option', { name: /mini兔兔/ })).toBeInTheDocument();
    await act(async () => resolveEarly?.({ ...formalKols, items: [formalKols.items[1]] }));

    await waitFor(() => expect(screen.queryByRole('option', { name: /韩国欧尼慧敏/ })).not.toBeInTheDocument());
    expect(screen.getByRole('option', { name: /mini兔兔/ })).toBeInTheDocument();
  });

  it('只导入所选达人的关联资料，切换达人仅移除关联资料并保留手工上传', async () => {
    const user = userEvent.setup();
    mockGetPersonaKolIntake
      .mockResolvedValueOnce({
        completed_at: '2026-07-29T18:20:00+08:00',
        formatted_answers: '【达人回答】我喜欢分享穿搭',
        report: '入驻报告正文',
      })
      .mockResolvedValueOnce(null);
    renderPage();

    await user.selectOptions(await screen.findByLabelText('目标达人（必填）'), '43');
    expect(await screen.findByText(/已找到最近完成的入驻资料/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '导入资料' }));
    expect(screen.getByText('关联入驻资料_mini兔兔')).toBeInTheDocument();

    await user.upload(screen.getByLabelText('上传达人资料'), new File(['手工'], 'manual.txt', { type: 'text/plain' }));
    expect(await screen.findByText('manual.txt')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('目标达人（必填）'), '56');

    expect(await screen.findByText('未找到已关联的入驻资料，可继续上传文件')).toBeInTheDocument();
    expect(screen.queryByText('关联入驻资料_mini兔兔')).not.toBeInTheDocument();
    expect(screen.getByText('manual.txt')).toBeInTheDocument();
  });

  it('快速切换达人时丢弃旧达人的迟到入驻资料响应', async () => {
    const user = userEvent.setup();
    let resolveKol43: ((value: {
      completed_at: string;
      formatted_answers: string;
      report: string;
    }) => void) | undefined;
    let resolveKol56: ((value: null) => void) | undefined;
    mockGetPersonaKolIntake.mockImplementation((kolId: number) => new Promise(resolve => {
      if (kolId === 43) resolveKol43 = resolve;
      if (kolId === 56) resolveKol56 = resolve;
    }));
    renderPage();

    await user.selectOptions(await screen.findByLabelText('目标达人（必填）'), '43');
    await user.selectOptions(screen.getByLabelText('目标达人（必填）'), '56');
    await act(async () => resolveKol56?.(null));
    expect(await screen.findByText('未找到已关联的入驻资料，可继续上传文件')).toBeInTheDocument();

    await act(async () => resolveKol43?.({
      completed_at: '2026-07-29T18:20:00+08:00',
      formatted_answers: '43 号的入驻资料',
      report: '43 号的入驻报告',
    }));

    await waitFor(() => expect(screen.queryByText('已找到最近完成的入驻资料')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '导入资料' })).not.toBeInTheDocument();
  });

  it('没有关联入驻资料时仍可上传并生成，生成请求携带选中的同一 kol_id', async () => {
    const user = userEvent.setup();
    renderPage();
    await selectKolAndUpload(user);

    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    await waitFor(() => expect(mockGeneratePersona).toHaveBeenCalledWith(
      expect.objectContaining({
        kol_id: 43,
        influencer_info: expect.stringContaining('手工上传的访谈正文'),
      }),
      expect.any(AbortSignal),
    ));
    await waitFor(() => expect(mockGetPersonaReportDetail).toHaveBeenCalledWith(88));
  });

  it('一次弹窗内两个待覆盖字段独立选择，默认均为保留', async () => {
    const user = userEvent.setup();
    mockGetPersonaReportDetail.mockResolvedValueOnce({
      id: 88,
      kol_id: 43,
      status: 'ready',
      profile_result: '新人格档案',
      plan_result: '新内容规划',
      sync_result: { persona: 'pending', content_plan: 'pending' },
      pending_overwrites: [
        { field: 'persona', current_summary: '旧人格档案', report_summary: '新人格档案' },
        { field: 'content_plan', current_summary: '旧内容规划', report_summary: '新内容规划' },
      ],
    });
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    const personaKeep = within(dialog).getByRole('radio', { name: '人格档案：保留原内容' });
    const planKeep = within(dialog).getByRole('radio', { name: '内容规划：保留原内容' });
    expect(personaKeep).toBeChecked();
    expect(planKeep).toBeChecked();
    await user.click(within(dialog).getByRole('radio', { name: '内容规划：覆盖为新报告' }));
    await user.click(within(dialog).getByRole('button', { name: '确认同步' }));

    await waitFor(() => expect(mockSyncPersonaReportDecisions).toHaveBeenCalledWith(88, {
      persona: 'keep',
      content_plan: 'overwrite',
    }));
  });

  it('关闭覆盖弹窗也为所有待处理字段提交 keep', async () => {
    const user = userEvent.setup();
    mockGetPersonaReportDetail.mockResolvedValueOnce({
      id: 88,
      kol_id: 43,
      status: 'ready',
      profile_result: '新人格档案',
      plan_result: '新内容规划',
      sync_result: { persona: 'pending', content_plan: 'pending' },
      pending_overwrites: [
        { field: 'persona', current_summary: '旧人格档案', report_summary: '新人格档案' },
        { field: 'content_plan', current_summary: '旧内容规划', report_summary: '新内容规划' },
      ],
    });
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));
    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    await user.click(within(dialog).getByRole('button', { name: '关闭并保留' }));

    await waitFor(() => expect(mockSyncPersonaReportDecisions).toHaveBeenCalledWith(88, {
      persona: 'keep',
      content_plan: 'keep',
    }));
  });
});
