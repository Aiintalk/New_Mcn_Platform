import { get } from './request';
import type { PagedData } from '../types/api';
import type { OperationLog, ExternalServiceLog, LogListParams } from '../types/log';

export async function getOperationLogs(params?: LogListParams): Promise<PagedData<OperationLog>> {
  return get<PagedData<OperationLog>>('/api/admin/logs/operation', params as Record<string, string | number | boolean | undefined>);
}

export async function getExternalLogs(params?: LogListParams): Promise<PagedData<ExternalServiceLog>> {
  return get<PagedData<ExternalServiceLog>>('/api/admin/logs/external', params as Record<string, string | number | boolean | undefined>);
}
