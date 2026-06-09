import { get, del } from './request';
import type { PagedData } from '../types/api';
import type { Output, OutputListParams, AdminOutputListParams } from '../types/output';

export async function getOutputs(params?: OutputListParams): Promise<PagedData<Output>> {
  return get<PagedData<Output>>('/api/outputs', params as Record<string, string | number | boolean | undefined>);
}

export async function getOutput(output_id: number): Promise<Output> {
  return get<Output>(`/api/outputs/${output_id}`);
}

export async function deleteOutput(output_id: number): Promise<void> {
  await del<null>(`/api/outputs/${output_id}`);
}

export async function adminGetOutputs(params?: AdminOutputListParams): Promise<PagedData<Output>> {
  return get<PagedData<Output>>('/api/admin/outputs', params as Record<string, string | number | boolean | undefined>);
}

export async function adminGetOutput(output_id: number): Promise<Output> {
  return get<Output>(`/api/admin/outputs/${output_id}`);
}

export async function adminDeleteOutput(output_id: number): Promise<void> {
  await del<null>(`/api/admin/outputs/${output_id}`);
}
