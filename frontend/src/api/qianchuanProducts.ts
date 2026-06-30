import { get, post, put, del } from './request';
import type { QianchuanProduct, QianchuanProductsPage } from '../types/kolWorkspace';

export const getQianchuanProducts = (params?: { page?: number; page_size?: number; q?: string }) =>
  get<QianchuanProductsPage>('/api/operator/qianchuan-products', params);

export const createQianchuanProduct = (data: Omit<QianchuanProduct, 'id' | 'created_by' | 'created_at' | 'updated_at'>) =>
  post<QianchuanProduct>('/api/operator/qianchuan-products', data);

export const updateQianchuanProduct = (id: number, data: Partial<QianchuanProduct>) =>
  put<QianchuanProduct>(`/api/operator/qianchuan-products/${id}`, data);

export const deleteQianchuanProduct = (id: number) =>
  del<{ id: number }>(`/api/operator/qianchuan-products/${id}`);
