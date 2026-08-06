import { App } from 'antd';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const originalGetComputedStyle = window.getComputedStyle.bind(window);

beforeAll(() => {
  vi.spyOn(window, 'getComputedStyle').mockImplementation(element => originalGetComputedStyle(element));
});

afterAll(() => {
  vi.restoreAllMocks();
});

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return { ...actual, message: { success: vi.fn(), error: vi.fn() } };
});

const {
  mockGetPersonaKols,
  mockGetPersonaKolIntake,
  mockParseFile,
  mockGeneratePersona,
  mockGetPersonaReports,
  mockGetPersonaReportDetail,
  mockSyncPersonaReportDecisions,
} = vi.hoisted(() => ({
  mockGetPersonaKols: vi.fn(),
  mockGetPersonaKolIntake: vi.fn(),
  mockParseFile: vi.fn(),
  mockGeneratePersona: vi.fn(),
  mockGetPersonaReports: vi.fn(),
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
  getPersonaReports: mockGetPersonaReports,
  getPersonaReportDetail: mockGetPersonaReportDetail,
  syncPersonaReportDecisions: mockSyncPersonaReportDecisions,
  deletePersonaReport: vi.fn(),
}));

import PersonaPage from '../../../pages/operator/PersonaPage';

function WorkspaceProbe() {
  const { kolId } = useParams();
  const location = useLocation();
  return <div>{`工作台红人 ${kolId} ${location.search}`}</div>;
}

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
  return render(<App><MemoryRouter initialEntries={['/workspace/persona-positioning']}><Routes>
    <Route path="/workspace/persona-positioning" element={<PersonaPage />} />
    <Route path="/kol-workspace/:kolId" element={<WorkspaceProbe />} />
    <Route path="/kol-hub" element={<div>红人列表已刷新</div>} />
  </Routes></MemoryRouter></App>);
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
    mockGetPersonaReports.mockResolvedValue([]);
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

  it('生成和同步成功后可进入同一 kol_id 工作台或返回列表', async () => {
    const user = userEvent.setup();
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    expect(await screen.findByRole('button', { name: '进入红人工作台' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '返回红人列表' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '进入红人工作台' }));
    expect(await screen.findByText('工作台红人 43 ?tab=persona')).toBeInTheDocument();
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

  it('已选达人被新搜索结果排除后仍保持可见且可继续生成', async () => {
    const user = userEvent.setup();
    mockGetPersonaKols.mockImplementation(({ keyword }: { keyword?: string }) => Promise.resolve(
      keyword
        ? { ...formalKols, items: [formalKols.items[1]], pagination: { ...formalKols.pagination, total: 1 } }
        : formalKols,
    ));
    renderPage();

    await user.selectOptions(await screen.findByLabelText('目标达人（必填）'), '43');
    await user.type(screen.getByPlaceholderText('搜索达人名称、账号或抖音号'), '慧敏');

    await waitFor(() => expect(mockGetPersonaKols).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      keyword: '慧敏',
    }));
    expect(screen.getByLabelText('目标达人（必填）')).toHaveValue('43');
    expect(screen.getByRole('option', { name: /mini兔兔.*兔兔日常.*6\/7/ })).toBeInTheDocument();
    expect(screen.getByText(/当前已选：mini兔兔.*兔兔日常/)).toBeInTheDocument();

    await user.upload(screen.getByLabelText('上传达人资料'), new File(['搜索后的材料'], 'after-search.txt', { type: 'text/plain' }));
    await screen.findByText('after-search.txt');
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));
    await waitFor(() => expect(mockGeneratePersona).toHaveBeenCalledWith(
      expect.objectContaining({ kol_id: 43 }),
      expect.any(AbortSignal),
    ));
  });

  it('可翻到第二页选择第 21 位达人，搜索时重置回第一页', async () => {
    const user = userEvent.setup();
    const pageTwoKol = {
      id: 77,
      name: '第21位达人',
      account_name: '第二页账号',
      douyin_id: 'page21',
      profile_filled_count: 5,
      profile_total: 7,
    };
    mockGetPersonaKols.mockImplementation(({ page, keyword }: { page: number; keyword?: string }) => {
      if (keyword) {
        return Promise.resolve({
          items: [formalKols.items[0]],
          pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
        });
      }
      return Promise.resolve(page === 2
        ? {
            items: [pageTwoKol],
            pagination: { page: 2, page_size: 20, total: 21, total_pages: 2 },
          }
        : {
            ...formalKols,
            pagination: { page: 1, page_size: 20, total: 21, total_pages: 2 },
          });
    });
    renderPage();

    await screen.findByRole('option', { name: /mini兔兔/ });
    await user.click(screen.getByRole('button', { name: '下一页' }));
    await waitFor(() => expect(mockGetPersonaKols).toHaveBeenLastCalledWith({
      page: 2,
      page_size: 20,
      keyword: undefined,
    }));
    await user.selectOptions(await screen.findByLabelText('目标达人（必填）'), '77');
    expect(screen.getByLabelText('目标达人（必填）')).toHaveValue('77');

    await user.type(screen.getByPlaceholderText('搜索达人名称、账号或抖音号'), '兔兔');
    await waitFor(() => expect(mockGetPersonaKols).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      keyword: '兔兔',
    }));
    expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument();
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

  it('报告详情无待覆盖字段时，将每个同步动作显示为中文字段名和中文结果', async () => {
    const user = userEvent.setup();
    mockGetPersonaReportDetail
      .mockResolvedValueOnce({
        id: 88,
        kol_id: 43,
        status: 'ready',
        profile_result: '新人格档案',
        plan_result: '新内容规划',
        sync_result: { persona: 'auto_written', content_plan: 'unchanged' },
        pending_overwrites: [],
      })
      .mockResolvedValueOnce({
        id: 88,
        kol_id: 43,
        status: 'ready',
        profile_result: '新人格档案',
        plan_result: '新内容规划',
        sync_result: { persona: 'pending', content_plan: 'kept' },
        pending_overwrites: [],
      });
    const firstView = renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      '档案同步完成：人格档案 已自动写入；内容规划 未变化',
    );
    expect(screen.queryByText(/auto_written|unchanged/)).not.toBeInTheDocument();
    firstView.unmount();

    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      '档案同步完成：人格档案 待确认；内容规划 已保留',
    );
    expect(screen.queryByText(/pending|kept/)).not.toBeInTheDocument();
  });

  it('生成期间正式达人被删除时显示失败原因且不进入覆盖确认', async () => {
    const user = userEvent.setup();
    mockGetPersonaReportDetail.mockResolvedValueOnce({
      id: 88,
      kol_id: 43,
      status: 'failed',
      failure_reason: 'kol_deleted',
      profile_result: null,
      plan_result: null,
      sync_result: {},
      pending_overwrites: [],
    });
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      '对应红人已不存在，本次结果未写入',
    );
    expect(screen.queryByRole('dialog', { name: '确认同步人格定位结果' })).not.toBeInTheDocument();
  });

  it('定位同步或事实补全失败时显示真实失败提示，不伪报自动写入成功', async () => {
    const user = userEvent.setup();
    mockGetPersonaReportDetail.mockResolvedValueOnce({
      id: 88,
      kol_id: 43,
      status: 'ready',
      profile_result: '新人格档案',
      plan_result: '新内容规划',
      sync_result: { persona: 'auto_written', content_plan: 'auto_written' },
      pending_overwrites: [],
      positioning_sync_failed: true,
      fact_sync_failed: true,
    });
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('报告已生成，档案同步失败，请稍后重试');
    expect(status).toHaveTextContent('报告已生成，人物素材未能自动补全');
    expect(status).not.toHaveTextContent('已自动写入');
  });

  it('从历史重新打开报告时恢复逐字段覆盖确认，且默认保留', async () => {
    const user = userEvent.setup();
    mockGetPersonaReports.mockResolvedValueOnce([{
      id: 77,
      kol_id: 43,
      influencer_name: '历史达人',
      douyin_nickname: null,
      status: 'ready',
      created_at: '2026-08-03T09:00:00+08:00',
    }]);
    mockGetPersonaReportDetail.mockResolvedValueOnce({
      id: 77,
      kol_id: 43,
      status: 'ready',
      profile_result: '历史新人格',
      plan_result: '历史新规划',
      sync_result: { persona: 'pending', content_plan: 'pending' },
      pending_overwrites: [
        { field: 'persona', current_summary: '当前人格', report_summary: '历史新人格' },
        { field: 'content_plan', current_summary: '当前规划', report_summary: '历史新规划' },
      ],
    });
    renderPage();
    await user.click(screen.getByRole('button', { name: '历史记录' }));
    await user.click(await screen.findByText('历史达人'));

    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    expect(within(dialog).getByRole('radio', { name: '人格档案：保留原内容' })).toBeChecked();
    expect(within(dialog).getByRole('radio', { name: '内容规划：保留原内容' })).toBeChecked();
    expect(screen.getAllByText('历史新人格')).toHaveLength(2);
  });

  it('重新开始后丢弃旧报告详情的迟到响应，并只向新报告提交同步决定', async () => {
    const user = userEvent.setup();
    let resolveReport88: ((value: Record<string, unknown>) => void) | undefined;
    let resolveReport99: ((value: Record<string, unknown>) => void) | undefined;
    mockGeneratePersona
      .mockResolvedValueOnce({ reader: doneReader(), reportId: 88 })
      .mockResolvedValueOnce({ reader: doneReader(), reportId: 99 });
    mockGetPersonaReportDetail.mockImplementation((id: number) => new Promise(resolve => {
      if (id === 88) resolveReport88 = resolve;
      if (id === 99) resolveReport99 = resolve;
    }));
    renderPage();

    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));
    await waitFor(() => expect(mockGetPersonaReportDetail).toHaveBeenCalledWith(88));
    await user.click(screen.getByRole('button', { name: '重新开始' }));

    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));
    await waitFor(() => expect(mockGetPersonaReportDetail).toHaveBeenCalledWith(99));
    await act(async () => resolveReport99?.({
      id: 99,
      kol_id: 43,
      status: 'ready',
      profile_result: '99 新人格档案',
      plan_result: '99 新内容规划',
      sync_result: { persona: 'pending' },
      pending_overwrites: [
        { field: 'persona', current_summary: '99 当前档案', report_summary: '99 新报告' },
      ],
    }));
    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    expect(within(dialog).getByText('99 新报告')).toBeInTheDocument();

    await act(async () => resolveReport88?.({
      id: 88,
      kol_id: 43,
      status: 'ready',
      profile_result: '88 旧人格档案',
      plan_result: '88 旧内容规划',
      sync_result: { persona: 'pending' },
      pending_overwrites: [
        { field: 'persona', current_summary: '88 当前档案', report_summary: '88 迟到旧报告' },
      ],
    }));
    expect(within(dialog).queryByText('88 迟到旧报告')).not.toBeInTheDocument();
    expect(within(dialog).getByText('99 新报告')).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: '确认同步' }));
    await waitFor(() => expect(mockSyncPersonaReportDecisions).toHaveBeenCalledWith(99, {
      persona: 'keep',
    }));
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

  it('提交字段决定后，使用接口返回的逐字段动作显示同步结果', async () => {
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
    mockSyncPersonaReportDecisions.mockResolvedValueOnce({
      report_id: 88,
      fields: { persona: 'overwritten', content_plan: 'kept' },
    });
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    await user.click(within(dialog).getByRole('button', { name: '确认同步' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      '档案同步完成：人格档案 已覆盖；内容规划 已保留',
    );
    expect(screen.queryByText(/overwritten|kept|档案同步决定已提交/)).not.toBeInTheDocument();
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

  it('关闭并保留提交失败后先显示全保留，重试不会恢复旧覆盖选择', async () => {
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
    mockSyncPersonaReportDecisions
      .mockRejectedValueOnce(new Error('首次提交失败'))
      .mockResolvedValueOnce({});
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    await user.click(within(dialog).getByRole('radio', { name: '人格档案：覆盖为新报告' }));
    await user.click(within(dialog).getByRole('button', { name: '关闭并保留' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('档案同步失败，请重试');
    expect(within(dialog).getByRole('radio', { name: '人格档案：保留原内容' })).toBeChecked();
    expect(within(dialog).getByRole('radio', { name: '内容规划：保留原内容' })).toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: '确认同步' }));

    await waitFor(() => expect(mockSyncPersonaReportDecisions).toHaveBeenNthCalledWith(2, 88, {
      persona: 'keep',
      content_plan: 'keep',
    }));
  });

  it('覆盖确认使用标准模态框，按 Escape 等同关闭并保留', async () => {
    const user = userEvent.setup();
    mockGetPersonaReportDetail.mockResolvedValueOnce({
      id: 88,
      kol_id: 43,
      status: 'ready',
      profile_result: '新人格档案',
      plan_result: '新内容规划',
      sync_result: { persona: 'pending' },
      pending_overwrites: [
        { field: 'persona', current_summary: '旧人格档案', report_summary: '新人格档案' },
      ],
    });
    renderPage();
    await selectKolAndUpload(user);
    await user.click(screen.getByRole('button', { name: '下一步' }));
    await user.click(screen.getByRole('button', { name: '跳过，直接生成' }));

    const dialog = await screen.findByRole('dialog', { name: '确认同步人格定位结果' });
    expect(dialog).toHaveClass('ant-modal');
    const modalWrap = dialog.closest('.ant-modal-wrap');
    expect(modalWrap).not.toBeNull();
    fireEvent.keyDown(modalWrap as Element, { key: 'Escape', keyCode: 27 });

    await waitFor(() => expect(mockSyncPersonaReportDecisions).toHaveBeenCalledWith(88, {
      persona: 'keep',
    }));
  });
});
