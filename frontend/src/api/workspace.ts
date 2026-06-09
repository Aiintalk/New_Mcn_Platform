import { get, patch } from './request';
import type { WorkspaceTool } from '../types/workspace';

export async function getTools(): Promise<WorkspaceTool[]> {
  const data = await get<{ items: WorkspaceTool[] }>('/api/workspace/tools');
  return data.items;
}

export async function getTool(tool_code: string): Promise<WorkspaceTool> {
  return get<WorkspaceTool>(`/api/workspace/tools/${tool_code}`);
}

export async function adminGetTools(params?: { status?: string }): Promise<WorkspaceTool[]> {
  const data = await get<{ items: WorkspaceTool[] }>('/api/workspace/tools', params);
  return data.items;
}

export async function adminUpdateTool(
  tool_code: string,
  data: Partial<WorkspaceTool>
): Promise<WorkspaceTool> {
  return patch<WorkspaceTool>(`/api/admin/workspace/tools/${tool_code}`, data);
}
