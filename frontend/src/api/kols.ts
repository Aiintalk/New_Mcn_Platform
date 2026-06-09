import { get, post, patch, del } from './request';
import type { Kol, KolDetail, KolListParams, CreateKolRequest, UpdateKolRequest } from '../types/kol';
import type { PagedData } from '../types/api';

export async function getKols(params?: KolListParams): Promise<PagedData<Kol>> {
  return get<PagedData<Kol>>('/api/admin/kols', params as Record<string, string | number | boolean | undefined>);
}

export async function createKol(data: CreateKolRequest): Promise<Kol> {
  return post<Kol>('/api/admin/kols', data);
}

export async function getKol(id: number): Promise<KolDetail> {
  return get<KolDetail>(`/api/admin/kols/${id}`);
}

export async function updateKol(id: number, data: UpdateKolRequest): Promise<Kol> {
  return patch<Kol>(`/api/admin/kols/${id}`, data);
}

export async function deleteKol(id: number): Promise<void> {
  await del<null>(`/api/admin/kols/${id}`);
}

export async function fetchTikhub(id: number): Promise<KolDetail> {
  const result = await post<{ kol: KolDetail; tikhub: unknown }>(`/api/admin/kols/${id}/fetch-tikhub`);
  return result.kol;
}
