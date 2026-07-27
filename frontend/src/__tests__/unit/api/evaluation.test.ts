import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet, mockPost, mockPut, mockDel } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockDel: vi.fn(),
}));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  post: mockPost,
  put: mockPut,
  del: mockDel,
}));

import {
  listTestCases,
  createTestCase,
  updateTestCase,
  deleteTestCase,
  listVersionsAdmin,
  listVersionsOperator,
  getVersion,
  createVersion,
  deleteVersion,
  cloneVersion,
  triggerRun,
  getRun,
  listRuns,
  listRunScores,
  submitHumanLabel,
  compareRuns,
  listDimensions,
  createDimension,
  updateDimension,
  deleteDimension,
  listRubrics,
  replaceRubrics,
  listSchedulePolicies,
  createSchedulePolicy,
  updateSchedulePolicy,
  deleteSchedulePolicy,
  deriveDirection,
} from '../../../evaluation/api';

describe('evaluation API — 测试样本 (operator)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('listTestCases calls GET /api/operator/evaluation/test-cases with params', async () => {
    const data = { items: [], total: 0, page: 1, page_size: 20 };
    mockGet.mockResolvedValue(data);
    const result = await listTestCases({ page: 1, page_size: 20, tag: 'skincare' });
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/test-cases', {
      page: 1,
      page_size: 20,
      tag: 'skincare',
    });
    expect(result).toEqual(data);
  });

  it('listTestCases defaults to empty params', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0 });
    await listTestCases();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/test-cases', {});
  });

  it('createTestCase calls POST test-cases', async () => {
    mockPost.mockResolvedValue({ id: 1 });
    await createTestCase({ name: 'x', input_payload: {} } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/operator/evaluation/test-cases', {
      name: 'x',
      input_payload: {},
    });
  });

  it('updateTestCase calls PUT test-cases/:id', async () => {
    mockPut.mockResolvedValue({ id: 7 });
    await updateTestCase(7, { name: 'y' } as never);
    expect(mockPut).toHaveBeenCalledWith('/api/operator/evaluation/test-cases/7', { name: 'y' });
  });

  it('deleteTestCase calls DELETE test-cases/:id', async () => {
    mockDel.mockResolvedValue({ id: 7, deleted_at: 't' });
    await deleteTestCase(7);
    expect(mockDel).toHaveBeenCalledWith('/api/operator/evaluation/test-cases/7');
  });
});

describe('evaluation API — 版本 (admin/operator)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('listVersionsAdmin calls GET admin/versions with tool_code when provided', async () => {
    mockGet.mockResolvedValue([]);
    await listVersionsAdmin('qianchuan-writer');
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/versions', {
      tool_code: 'qianchuan-writer',
    });
  });

  it('listVersionsAdmin calls GET admin/versions with undefined when no filter', async () => {
    mockGet.mockResolvedValue([]);
    await listVersionsAdmin();
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/versions', undefined);
  });

  it('listVersionsOperator calls GET operator/versions', async () => {
    mockGet.mockResolvedValue([]);
    await listVersionsOperator();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/versions', undefined);
  });

  it('listVersionsOperator 传 toolCode 时带 query', async () => {
    mockGet.mockResolvedValue([]);
    await listVersionsOperator('qianchuan-writer');
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/versions', {
      tool_code: 'qianchuan-writer',
    });
  });

  it('getVersion calls GET admin/versions/:id', async () => {
    mockGet.mockResolvedValue({ id: 3 });
    await getVersion(3);
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/versions/3');
  });

  it('createVersion calls POST admin/versions', async () => {
    mockPost.mockResolvedValue({ id: 1 });
    await createVersion({ tool_code: 'qianchuan-writer', name: 'v1' } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/evaluation/versions', {
      tool_code: 'qianchuan-writer',
      name: 'v1',
    });
  });

  it('deleteVersion calls DELETE admin/versions/:id', async () => {
    mockDel.mockResolvedValue({ id: 1, deleted_at: 't' });
    await deleteVersion(1);
    expect(mockDel).toHaveBeenCalledWith('/api/admin/evaluation/versions/1');
  });

  it('cloneVersion calls POST admin/versions/:id/clone', async () => {
    mockPost.mockResolvedValue({ id: 2 });
    await cloneVersion(1, { name: 'v2' } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/evaluation/versions/1/clone', { name: 'v2' });
  });
});

describe('evaluation API — 运行 + 评分 (operator)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('triggerRun calls POST operator/runs', async () => {
    mockPost.mockResolvedValue({ id: 10 });
    await triggerRun({ version_id: 1, trigger_type: 'manual' } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/operator/evaluation/runs', {
      version_id: 1,
      trigger_type: 'manual',
    });
  });

  it('listRuns calls GET operator/runs with pagination + filter params', async () => {
    mockGet.mockResolvedValue({ items: [], pagination: { total: 0 } });
    await listRuns({ page: 2, page_size: 20, status: 'completed', version_id: 5 });
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/runs', {
      page: 2,
      page_size: 20,
      status: 'completed',
      version_id: 5,
    });
  });

  it('listRuns defaults to empty params', async () => {
    mockGet.mockResolvedValue({ items: [], pagination: { total: 0 } });
    await listRuns();
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/runs', {});
  });

  it('getRun calls GET operator/runs/:id', async () => {
    mockGet.mockResolvedValue({ id: 10 });
    await getRun(10);
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/runs/10');
  });

  it('listRunScores calls GET operator/runs/:id/scores', async () => {
    mockGet.mockResolvedValue([]);
    await listRunScores(10);
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/runs/10/scores');
  });

  it('submitHumanLabel calls PUT operator/scores/:id/human-label', async () => {
    mockPut.mockResolvedValue({ id: 5 });
    await submitHumanLabel(5, { new_score: 9, feedback: 'ok' } as never);
    expect(mockPut).toHaveBeenCalledWith('/api/operator/evaluation/scores/5/human-label', {
      new_score: 9,
      feedback: 'ok',
    });
  });

  it('compareRuns calls GET operator/compare with run_a/run_b', async () => {
    mockGet.mockResolvedValue({});
    await compareRuns(1, 2);
    expect(mockGet).toHaveBeenCalledWith('/api/operator/evaluation/compare', {
      run_a: 1,
      run_b: 2,
    });
  });
});

describe('evaluation API — 维度 + Rubric (admin)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('listDimensions calls GET admin/dimensions with tool_code when provided', async () => {
    mockGet.mockResolvedValue([]);
    await listDimensions('qianchuan-writer');
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/dimensions', {
      tool_code: 'qianchuan-writer',
    });
  });

  it('listDimensions calls GET admin/dimensions with undefined when no filter', async () => {
    mockGet.mockResolvedValue([]);
    await listDimensions();
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/dimensions', undefined);
  });

  it('createDimension calls POST admin/dimensions', async () => {
    mockPost.mockResolvedValue({ id: 1 });
    await createDimension({ tool_code: 'qianchuan-writer', name: 'quality' } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/evaluation/dimensions', {
      tool_code: 'qianchuan-writer',
      name: 'quality',
    });
  });

  it('updateDimension calls PUT admin/dimensions/:id', async () => {
    mockPut.mockResolvedValue({ id: 1 });
    await updateDimension(1, { default_weight: 0.5 } as never);
    expect(mockPut).toHaveBeenCalledWith('/api/admin/evaluation/dimensions/1', {
      default_weight: 0.5,
    });
  });

  it('deleteDimension calls DELETE admin/dimensions/:id', async () => {
    mockDel.mockResolvedValue({ id: 1, deleted_at: 't' });
    await deleteDimension(1);
    expect(mockDel).toHaveBeenCalledWith('/api/admin/evaluation/dimensions/1');
  });

  it('listRubrics calls GET admin/dimensions/:id/rubrics', async () => {
    mockGet.mockResolvedValue([]);
    await listRubrics(1);
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/dimensions/1/rubrics');
  });

  it('replaceRubrics calls PUT admin/dimensions/:id/rubrics', async () => {
    mockPut.mockResolvedValue([]);
    await replaceRubrics(1, { rubrics: [] } as never);
    expect(mockPut).toHaveBeenCalledWith('/api/admin/evaluation/dimensions/1/rubrics', {
      rubrics: [],
    });
  });
});

describe('evaluation API — 定时策略 (admin)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('listSchedulePolicies calls GET admin/schedule-policies', async () => {
    mockGet.mockResolvedValue([]);
    await listSchedulePolicies();
    expect(mockGet).toHaveBeenCalledWith('/api/admin/evaluation/schedule-policies');
  });

  it('createSchedulePolicy calls POST admin/schedule-policies', async () => {
    mockPost.mockResolvedValue({ id: 1 });
    await createSchedulePolicy({ name: 'daily', cron: '0 9 * * *', version_id: 1 } as never);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/evaluation/schedule-policies', {
      name: 'daily',
      cron: '0 9 * * *',
      version_id: 1,
    });
  });

  it('updateSchedulePolicy calls PUT admin/schedule-policies/:id', async () => {
    mockPut.mockResolvedValue({ id: 1 });
    await updateSchedulePolicy(1, { is_active: false } as never);
    expect(mockPut).toHaveBeenCalledWith('/api/admin/evaluation/schedule-policies/1', {
      is_active: false,
    });
  });

  it('deleteSchedulePolicy calls DELETE admin/schedule-policies/:id', async () => {
    mockDel.mockResolvedValue({ id: 1, deleted_at: 't' });
    await deleteSchedulePolicy(1);
    expect(mockDel).toHaveBeenCalledWith('/api/admin/evaluation/schedule-policies/1');
  });
});

describe('evaluation API — 工具函数', () => {
  it('deriveDirection returns flat when either score is null', () => {
    expect(deriveDirection(null, 1)).toBe('flat');
    expect(deriveDirection(1, null)).toBe('flat');
    expect(deriveDirection(null, null)).toBe('flat');
  });

  it('deriveDirection returns improve when delta > 0.05', () => {
    expect(deriveDirection(7, 8)).toBe('improve');
    expect(deriveDirection(7, 7.06)).toBe('improve');
  });

  it('deriveDirection returns worsen when delta < -0.05', () => {
    expect(deriveDirection(8, 7)).toBe('worsen');
    expect(deriveDirection(7, 6.94)).toBe('worsen');
  });

  it('deriveDirection returns flat when |delta| <= 0.05', () => {
    expect(deriveDirection(7, 7.05)).toBe('flat');
    expect(deriveDirection(7, 6.95)).toBe('flat');
    expect(deriveDirection(7, 7)).toBe('flat');
  });
});
