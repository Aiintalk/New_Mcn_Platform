import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet, mockDel } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockDel: vi.fn(),
}));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  del: mockDel,
}));

import { getOutputs, getOutput, deleteOutput, adminGetOutputs, adminGetOutput, adminDeleteOutput } from '../../../api/outputs';

describe('outputs API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getOutputs calls GET /api/outputs with params', async () => {
    const pagedData = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(pagedData);
    const result = await getOutputs({ page: 1, page_size: 10 });
    expect(mockGet).toHaveBeenCalledWith('/api/outputs', { page: 1, page_size: 10 });
    expect(result).toEqual(pagedData);
  });

  it('getOutput calls GET /api/outputs/:id', async () => {
    const output = { id: 1, title: 'Test Output', content: 'Hello' };
    mockGet.mockResolvedValue(output);
    const result = await getOutput(1);
    expect(mockGet).toHaveBeenCalledWith('/api/outputs/1');
    expect(result.id).toBe(1);
  });

  it('deleteOutput calls DELETE /api/outputs/:id', async () => {
    mockDel.mockResolvedValue(null);
    await deleteOutput(1);
    expect(mockDel).toHaveBeenCalledWith('/api/outputs/1');
  });

  it('adminGetOutputs calls GET /api/admin/outputs', async () => {
    const pagedData = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(pagedData);
    const result = await adminGetOutputs({ page: 1 });
    expect(mockGet).toHaveBeenCalledWith('/api/admin/outputs', { page: 1 });
    expect(result).toEqual(pagedData);
  });

  it('adminGetOutput calls GET /api/admin/outputs/:id', async () => {
    const output = { id: 2, title: 'Admin Output' };
    mockGet.mockResolvedValue(output);
    const result = await adminGetOutput(2);
    expect(mockGet).toHaveBeenCalledWith('/api/admin/outputs/2');
    expect(result.id).toBe(2);
  });

  it('adminDeleteOutput calls DELETE /api/admin/outputs/:id', async () => {
    mockDel.mockResolvedValue(null);
    await adminDeleteOutput(2);
    expect(mockDel).toHaveBeenCalledWith('/api/admin/outputs/2');
  });
});
