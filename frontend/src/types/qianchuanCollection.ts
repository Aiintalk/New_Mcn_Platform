export interface CollectionPersona {
  name: string;
  script_count: number;
}

export interface CollectionScript {
  id: number;
  pool: 'global' | 'persona';
  persona_name: string | null;
  title: string;
  content: string;
  likes: number | null;
  source: string | null;
  source_account: string | null;
  script_date: string | null;
  created_at: string;
}

export interface ScriptListResponse {
  scripts: CollectionScript[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateScriptBody {
  pool: 'global' | 'persona';
  persona_name?: string;
  title: string;
  content: string;
  likes?: number;
  source?: string;
  source_account?: string;
  script_date?: string;
}
