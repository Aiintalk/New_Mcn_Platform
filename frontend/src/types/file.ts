export interface FileRecord {
  id: number;
  file_name: string;
  file_type: string;
  tool_code: string;
  created_by: number;
  created_at: string;
}

export interface DownloadUrl {
  file_id: number;
  file_name: string;
  download_url: string;
  expires_in: number;
}
