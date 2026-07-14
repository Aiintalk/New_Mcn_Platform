import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';

const mockDeriveDirections = vi.fn();
const mockGenerateValueScript = vi.fn();
const mockIterateValueScript = vi.fn();

vi.mock('../../../api/valuesWriter', () => ({
  deriveDirections: (...args: unknown[]) => mockDeriveDirections(...args),
  generateValueScript: (...args: unknown[]) => mockGenerateValueScript(...args),
  iterateValueScript: (...args: unknown[]) => mockIterateValueScript(...args),
  saveOutput: vi.fn(),
}));
vi.mock('../../../api/kolWorkspace', () => ({
  getActiveProducts: vi.fn().mockResolvedValue([{ id: 8, nickname: '晚霜', core_selling_point: '紧致', mechanism: '买一送一', unique_selling: '独家', mechanism_exclusive: true }]),
  updateActiveProducts: vi.fn().mockResolvedValue({}),
}));
vi.mock('../../../api/qianchuanProducts', () => ({
  getQianchuanProducts: vi.fn().mockResolvedValue({ items: [{ id: 8, nickname: '晚霜', core_selling_point: '紧致', mechanism: '买一送一', unique_selling: '独家', mechanism_exclusive: true }], pagination: {} }),
}));
vi.mock('../../../api/request', () => ({ get: vi.fn().mockResolvedValue([]) }));
vi.mock('../../../store/authStore', () => ({ useAuthStore: { getState: () => ({ token: 'mock-token' }) } }));

import { ValuesWriterModule, calculateBigramSimilarity, parseValueScriptResult, similarityStatus } from '../../../pages/operator/ValuesWriterPage';

function renderModule() {
  return render(<App><ValuesWriterModule kolId={1} /></App>);
}

describe('ValuesWriterModule', () => {
  it('从锁定开头和爆款全文开始旧版四步流程', () => {
    renderModule();
    expect(screen.getByRole('heading', { name: '输入爆款原文' })).toBeInTheDocument();
    expect(screen.getByLabelText('锁定开头')).toBeInTheDocument();
    expect(screen.getByLabelText('爆款全文')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /下一步：选择产品/ })).toBeDisabled();
  });

  it('根据当前商品推导方向，并允许人工调整后生成', async () => {
    const user = userEvent.setup();
    mockDeriveDirections.mockResolvedValue({ directions: [{ type: '诱惑型', title: '被看见', description: '展示生活优势', anchor: '轻松被偏爱' }] });
    mockGenerateValueScript.mockImplementation(async (_body: unknown, onDelta: (value: string) => void) => {
      const value = '<analysis>总字数：30</analysis><rewrite>锁定开头\n全新表达</rewrite><report>开头核查通过</report>';
      onDelta(value);
      return value;
    });
    renderModule();
    await user.type(screen.getByLabelText('锁定开头'), '锁定开头');
    await user.type(screen.getByLabelText('爆款全文'), '锁定开头\n原文第二段');
    await user.click(screen.getByRole('button', { name: /下一步：选择产品/ }));
    await user.click(screen.getByRole('button', { name: '生成情绪方向' }));
    await screen.findByText('诱惑型 · 被看见');
    await user.click(screen.getByText('诱惑型 · 被看见'));
    await user.clear(screen.getByLabelText('方向标题'));
    await user.type(screen.getByLabelText('方向标题'), '人工标题');
    await user.clear(screen.getByLabelText('人工调整方向说明'));
    await user.type(screen.getByLabelText('人工调整方向说明'), '人工确认的方向');
    await user.click(screen.getByRole('button', { name: '生成脚本和报告' }));
    await screen.findByLabelText('改写脚本');
    expect(mockDeriveDirections).toHaveBeenCalledWith({ kol_id: 1, opening_line: '锁定开头', original_script: '锁定开头\n原文第二段' });
    expect(mockGenerateValueScript.mock.calls[0][0]).toMatchObject({ kol_id: 1, direction: { title: '人工标题', description: '人工确认的方向' } });
  });

  it('记录每次人工智能修改要求及更新后的脚本、报告和相似度', async () => {
    const user = userEvent.setup();
    mockDeriveDirections.mockResolvedValue({ directions: [{ type: '诱惑型', title: '被看见', description: '展示生活优势', anchor: '轻松被偏爱' }] });
    mockGenerateValueScript.mockImplementation(async (_body: unknown, onDelta: (value: string) => void) => {
      const value = '<analysis>初稿结构</analysis><rewrite>锁定开头\n初稿表达</rewrite><report>初稿报告</report>';
      onDelta(value);
      return value;
    });
    mockIterateValueScript.mockImplementation(async (_body: unknown, onDelta: (value: string) => void) => {
      const value = '<analysis>修改后结构</analysis><rewrite>锁定开头\n修改后表达</rewrite><report>修改后报告</report>';
      onDelta(value);
      return value;
    });
    renderModule();
    await user.type(screen.getByLabelText('锁定开头'), '锁定开头');
    await user.type(screen.getByLabelText('爆款全文'), '锁定开头\n原文第二段');
    await user.click(screen.getByRole('button', { name: /下一步：选择产品/ }));
    await user.click(screen.getByRole('button', { name: '生成情绪方向' }));
    await user.click(await screen.findByText('诱惑型 · 被看见'));
    await user.click(screen.getByRole('button', { name: '生成脚本和报告' }));
    await screen.findByLabelText('改写脚本');

    await user.type(screen.getByLabelText('修改要求'), '把语气改得更克制');
    await user.click(screen.getByRole('button', { name: '发送修改要求' }));

    expect(await screen.findByText('第 1 次 AI 修改')).toBeInTheDocument();
    expect(screen.getByLabelText('改写脚本')).toHaveValue('锁定开头\n修改后表达');
    expect(screen.getByText(/修改后报告/)).toBeInTheDocument();
    expect(screen.getByText(/与原文相似度：/)).toBeInTheDocument();
    expect(mockIterateValueScript).toHaveBeenCalledWith(expect.objectContaining({
      kol_id: 1,
      instruction: '把语气改得更克制',
      current_result: expect.objectContaining({ rewrite: '锁定开头\n初稿表达' }),
      history: [],
    }), expect.any(Function));
  });

  it('只接受完整的结构化生成结果，并按旧版双字算法给出百分比', () => {
    expect(parseValueScriptResult('<rewrite>脚本</rewrite><report>报告</report>')).toBeNull();
    expect(parseValueScriptResult('<analysis>结构</analysis><rewrite>脚本</rewrite><report>报告</report>')).toEqual({ analysis: '结构', rewrite: '脚本', report: '报告' });
    expect(calculateBigramSimilarity('甲乙丙丁', '甲乙戊己')).toBe(20);
  });

  it('按 35、36 至 50、超过 50 三档提示相似度风险', () => {
    expect(similarityStatus(35)).toBe('安全');
    expect(similarityStatus(36)).toBe('接近安全线');
    expect(similarityStatus(50)).toBe('接近安全线');
    expect(similarityStatus(51)).toBe('需要继续改写');
  });
});
