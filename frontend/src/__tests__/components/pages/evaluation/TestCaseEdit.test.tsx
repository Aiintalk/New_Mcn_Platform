/**
 * TestCaseEdit 页面测试（方案 A 纯业务数据四字段表单）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { App as AntApp } from 'antd';
import { MemoryRouter } from 'react-router-dom';

const mockGetTestCase = vi.fn();
const mockCreateTestCase = vi.fn();
const mockUpdateTestCase = vi.fn();

vi.mock('../../../../evaluation/api', () => ({
  getTestCase: (...args: unknown[]) => mockGetTestCase(...args),
  createTestCase: (...args: unknown[]) => mockCreateTestCase(...args),
  updateTestCase: (...args: unknown[]) => mockUpdateTestCase(...args),
}));

const mockUseParams = vi.fn();
const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
  };
});

import TestCaseEditPage from '../../../../evaluation/pages/TestCaseEdit';

function renderWithProviders(ui: React.ReactElement, initialEntries: string[] = ['/evaluation/test-cases/new']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <AntApp>{ui}</AntApp>
    </MemoryRouter>,
  );
}

/** 找指定 label 的表单控件 wrapper（antd Form.Item label 旁的控件） */
function fieldByLabel(labelText: string): HTMLElement {
  const labels = Array.from(document.querySelectorAll('label'));
  // 精确匹配（去必填星号/空白）：includes 会同时命中 '达人' 与 '达人人设' 造成错位
  const norm = (s: string) => s.replace(/\*/g, '').trim();
  const label = labels.find((l) => norm(l.textContent ?? '') === labelText);
  const item = label?.closest('.ant-form-item');
  const ctrl = item?.querySelector('input, textarea') as HTMLElement;
  if (!ctrl) throw new Error(`未找到字段控件: ${labelText}`);
  return ctrl;
}

const sampleExisting = {
  id: 22, tool_code: 'qianchuan-writer',
  name: '暖暖 · 酵色隔离 ①',
  description: '张翀真实测试集',
  input_payload: {
    name: '暖暖',
    persona: '语气温柔、强调干净利落的造型和高级感',
    product_info: '机制：58/瓶；108到手2瓶…',
    original_script: '詹詹、小猴子都在推荐的这款TAG酵色隔离…',
  },
  tags: ['真实数据'],
  is_active: true,
  created_by: null, updated_by: null,
  created_at: 't', updated_at: 't', deleted_at: null,
};

function fillAllFields() {
  setFieldValueField('样本名称', '测试样本A');
  setFieldValueField('达人', '羊羊');
  setFieldValueField('达人人设', '亲和力节奏快');
  setFieldValueField('产品信息', '面膜 199/10盒');
  setFieldValueField('参考原版脚本', '我把美迪惠尔面膜砍到一盒18块钱');
}
function setFieldValueField(label: string, value: string) {
  const ctrl = fieldByLabel(label);
  const proto = ctrl instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')!.set!;
  setter.call(ctrl, value);
  ctrl.dispatchEvent(new Event('input', { bubbles: true }));
}

function addTag(text: string) {
  const tagInput = Array.from(document.querySelectorAll('input'))
    .find((i) => i.placeholder === '输入后回车') as HTMLInputElement;
  setFieldValueDirect(tagInput, text);
  fireEvent.keyDown(tagInput, { key: 'Enter' });
}
function setFieldValueDirect(el: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!;
  setter.call(el, value);
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

describe('TestCaseEditPage（方案 A 四字段）', () => {
  beforeEach(() => {
    mockGetTestCase.mockReset();
    mockCreateTestCase.mockReset();
    mockUpdateTestCase.mockReset();
    mockUseParams.mockReset();
    mockUseParams.mockReturnValue({ id: 'new' });
    mockNavigate.mockReset();
  });

  it('新建模式渲染四字段表单（回归：旧表单 selling_points/messages 已移除）', async () => {
    renderWithProviders(<TestCaseEditPage />);
    expect(screen.getByText('新建测试样本')).toBeInTheDocument();
    expect(screen.getByText('基础信息')).toBeInTheDocument();
    expect(screen.getByText(/业务输入/)).toBeInTheDocument();
    expect(screen.getByText('标签')).toBeInTheDocument();
    // 旧字段不复存在
    expect(screen.queryByText('产品卖点卡')).not.toBeInTheDocument();
    expect(screen.queryByText(/对话上下文/)).not.toBeInTheDocument();
  });

  it('四业务字段齐填 + 标签 → 保存调用 createTestCase（input_payload 只含四字段，无 messages）', async () => {
    mockCreateTestCase.mockResolvedValue(sampleExisting);
    renderWithProviders(<TestCaseEditPage />);
    await waitFor(() => screen.getByText('基础信息'));
    fillAllFields();
    addTag('真实数据');
    const saveBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => (b.textContent ?? '').replace(/\s/g, '') === '保存');
    fireEvent.click(saveBtn!);
    await waitFor(() => {
      expect(mockCreateTestCase).toHaveBeenCalledTimes(1);
    });
    const body = mockCreateTestCase.mock.calls[0][0] as Record<string, unknown>;
    const ip = body.input_payload as Record<string, unknown>;
    expect(ip.name).toBe('羊羊');
    expect(ip.persona).toBe('亲和力节奏快');
    expect(ip.product_info).toBe('面膜 199/10盒');
    expect(ip.original_script).toBe('我把美迪惠尔面膜砍到一盒18块钱');
    expect(ip.messages).toBeUndefined();   // 方案 A：无指令字段
    expect(body.tags).toEqual(['真实数据']);
  });

  it('未加标签提交时阻止并提示', async () => {
    renderWithProviders(<TestCaseEditPage />);
    await waitFor(() => screen.getByText('基础信息'));
    fillAllFields();
    const saveBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => (b.textContent ?? '').replace(/\s/g, '') === '保存');
    fireEvent.click(saveBtn!);
    await waitFor(() => {
      expect(document.querySelector('.ant-message-notice')?.textContent).toContain('标签');
    });
    expect(mockCreateTestCase).not.toHaveBeenCalled();
  });

  it('编辑模式：按方案 A 契约回填四字段（回归：旧表单字段错位显示空）', async () => {
    mockUseParams.mockReturnValue({ id: '22' });
    mockGetTestCase.mockResolvedValue(sampleExisting);
    renderWithProviders(<TestCaseEditPage />, ['/evaluation/test-cases/22/edit']);
    await waitFor(() => screen.getByDisplayValue('暖暖 · 酵色隔离 ①'));
    // 四业务字段从 input_payload 正确回填（非空）
    expect((fieldByLabel('达人') as HTMLInputElement).value).toBe('暖暖');
    expect((fieldByLabel('达人人设') as HTMLTextAreaElement).value).toContain('语气温柔');
    expect((fieldByLabel('产品信息') as HTMLTextAreaElement).value).toContain('58/瓶');
    expect((fieldByLabel('参考原版脚本') as HTMLTextAreaElement).value).toContain('酵色隔离');
    expect(screen.getByText('真实数据')).toBeInTheDocument();  // tags 回填
  });

  it('编辑保存调用 updateTestCase 且不破坏四字段', async () => {
    mockUseParams.mockReturnValue({ id: '22' });
    mockGetTestCase.mockResolvedValue(sampleExisting);
    mockUpdateTestCase.mockResolvedValue(sampleExisting);
    renderWithProviders(<TestCaseEditPage />, ['/evaluation/test-cases/22/edit']);
    await waitFor(() => screen.getByDisplayValue('暖暖 · 酵色隔离 ①'));
    const saveBtn = Array.from(document.querySelectorAll('button'))
      .find((b) => (b.textContent ?? '').replace(/\s/g, '') === '保存');
    fireEvent.click(saveBtn!);
    await waitFor(() => {
      expect(mockUpdateTestCase).toHaveBeenCalledWith(22, expect.objectContaining({
        input_payload: expect.objectContaining({
          name: '暖暖',
          persona: expect.stringContaining('语气温柔'),
        }),
      }));
    });
  });

  it('标签边界：重复标签只保留一个；空输入不添加', async () => {
    renderWithProviders(<TestCaseEditPage />);
    await waitFor(() => screen.getByText('基础信息'));
    addTag('真实数据');
    addTag('真实数据');
    expect(screen.getAllByText('真实数据').length).toBe(1);
    addTag('  ');
    expect(screen.getAllByText('真实数据').length).toBe(1);
  });

  it('加载失败时 message.error 提示', async () => {
    mockUseParams.mockReturnValue({ id: '999' });
    mockGetTestCase.mockRejectedValue(new Error('not found'));
    renderWithProviders(<TestCaseEditPage />, ['/evaluation/test-cases/999/edit']);
    await waitFor(() => {
      expect(document.querySelector('.ant-message-notice')?.textContent).toContain('not found');
    });
  });
});
