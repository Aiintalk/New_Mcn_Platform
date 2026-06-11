import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet, mockPatch } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPatch: vi.fn(),
}));

vi.mock('../../../api/request', () => ({
  get: mockGet,
  patch: mockPatch,
}));

import { getTools, getTool, adminGetTools, adminUpdateTool } from '../../../api/workspace';

describe('workspace API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getTools calls GET /api/workspace/tools and returns items', async () => {
    const tools = [{ id: 1, tool_code: 'persona-writer', tool_name: '人设脚本仿写', status: 'online' }];
    mockGet.mockResolvedValue({ items: tools });
    const result = await getTools();
    expect(mockGet).toHaveBeenCalledWith('/api/workspace/tools');
    expect(result).toEqual(tools);
  });

  it('getTool calls GET /api/workspace/tools/:code', async () => {
    const tool = { id: 1, tool_code: 'persona-writer', tool_name: '人设脚本仿写', status: 'online' };
    mockGet.mockResolvedValue(tool);
    const result = await getTool('persona-writer');
    expect(mockGet).toHaveBeenCalledWith('/api/workspace/tools/persona-writer');
    expect(result.tool_code).toBe('persona-writer');
  });

  it('adminGetTools calls GET /api/workspace/tools with status filter', async () => {
    mockGet.mockResolvedValue({ items: [] });
    await adminGetTools({ status: 'online' });
    expect(mockGet).toHaveBeenCalledWith('/api/workspace/tools', { status: 'online' });
  });

  it('adminUpdateTool calls PATCH /api/admin/workspace/tools/:code', async () => {
    mockPatch.mockResolvedValue({ id: 1, tool_code: 'persona-writer', status: 'offline' });
    const result = await adminUpdateTool('persona-writer', { status: 'offline' });
    expect(mockPatch).toHaveBeenCalledWith('/api/admin/workspace/tools/persona-writer', { status: 'offline' });
    expect(result.status).toBe('offline');
  });
});
