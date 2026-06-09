import { get, del } from './request';
import type { PagedData } from '../types/api';

export interface FileItem {
  id: number;
  filename: string;
  file_type: string;
  file_size: number | null;
  content_type: string | null;
  output_id: number | null;
  task_id: number | null;
  created_by: number;
  created_at: string;
}

export interface DownloadUrlResponse {
  file_id: number;
  file_name: string;
  download_url: string;
  expires_in: number;
}

export async function getFiles(params?: { output_id?: number; page?: number; page_size?: number }): Promise<PagedData<FileItem>> {
  return get<PagedData<FileItem>>('/api/files', params as Record<string, string | number | boolean | undefined>);
}

export async function getDownloadUrl(file_id: number): Promise<DownloadUrlResponse> {
  return get<DownloadUrlResponse>(`/api/files/${file_id}/download-url`);
}

export async function deleteFile(file_id: number): Promise<void> {
  await del<null>(`/api/files/${file_id}`);
}
