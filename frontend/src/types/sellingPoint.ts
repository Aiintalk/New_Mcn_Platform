export interface UploadedFile {
  name: string;
  text: string;
}

export interface HistoryItem {
  id: string;
  productName: string;
  createdAt: string;
  summary: string;
}

export interface HistoryRecord {
  id: string;
  productName: string;
  result: string;
  chatHistory: Array<{ role: string; content: string }>;
  briefFiles: UploadedFile[];
  scriptFiles: UploadedFile[];
  createdAt: string;
}

export interface SellingPointConfig {
  id: number;
  config_key: string;
  ai_model_id: number | null;
  system_prompt: string;
  is_active: boolean;
  updated_at: string;
}
