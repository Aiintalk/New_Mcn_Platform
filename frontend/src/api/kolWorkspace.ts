import { get, post, put, del } from './request';
import type {
  WorkspaceDashboardData, KolBenchmark, QianchuanProduct, PersonaDetails,
} from '../types/kolWorkspace';

// 首页聚合
export const getWorkspaceDashboard = (kolId: number) =>
  get<WorkspaceDashboardData>(`/api/operator/workspace/${kolId}/dashboard`);

// 对标账号
export const getBenchmarks = (kolId: number) =>
  get<{ content: KolBenchmark[]; livestream: KolBenchmark[] }>(`/api/operator/workspace/${kolId}/benchmarks`);

export const createBenchmark = (kolId: number, data: Omit<KolBenchmark, 'id' | 'kol_id'>) =>
  post<KolBenchmark>(`/api/operator/workspace/${kolId}/benchmarks`, data);

export const updateBenchmark = (kolId: number, id: number, data: Partial<KolBenchmark>) =>
  put<KolBenchmark>(`/api/operator/workspace/${kolId}/benchmarks/${id}`, data);

export const deleteBenchmark = (kolId: number, id: number) =>
  del<{ id: number }>(`/api/operator/workspace/${kolId}/benchmarks/${id}`);

// 在售商品
export const getActiveProducts = (kolId: number) =>
  get<QianchuanProduct[]>(`/api/operator/workspace/${kolId}/active-products`);

export const updateActiveProducts = (kolId: number, productIds: number[]) =>
  put<{ active_product_ids: number[] }>(`/api/operator/workspace/${kolId}/active-products`, { product_ids: productIds });

// 人物档案
export const getPersonaDetails = (kolId: number) =>
  get<PersonaDetails>(`/api/operator/kols/${kolId}/persona-details`);

export const updatePersonaDetails = (kolId: number, data: Partial<PersonaDetails>) =>
  put<PersonaDetails>(`/api/operator/kols/${kolId}/persona-details`, data);
