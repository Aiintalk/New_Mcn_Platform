import { get, post, patch, del } from './request';
import type { PagedData } from '../types/api';
import type { ServiceCredential, CreateCredentialRequest, UpdateCredentialRequest } from '../types/credential';

export async function getCredentials(provider?: string): Promise<PagedData<ServiceCredential>> {
  return get<PagedData<ServiceCredential>>('/api/admin/config/credentials', provider ? { provider } : undefined);
}

export async function createCredential(data: CreateCredentialRequest): Promise<ServiceCredential> {
  return post<ServiceCredential>('/api/admin/config/credentials', data);
}

export async function updateCredential(id: number, data: UpdateCredentialRequest): Promise<ServiceCredential> {
  return patch<ServiceCredential>(`/api/admin/config/credentials/${id}`, data);
}

export async function deleteCredential(id: number): Promise<void> {
  await del<null>(`/api/admin/config/credentials/${id}`);
}

export async function enableCredential(id: number): Promise<void> {
  await post<null>(`/api/admin/config/credentials/${id}/enable`);
}

export async function disableCredential(id: number): Promise<void> {
  await post<null>(`/api/admin/config/credentials/${id}/disable`);
}
