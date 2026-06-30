// 千川产品
export interface QianchuanProduct {
  id: number;
  nickname: string;
  core_selling_point: string | null;
  visualization: string | null;
  mechanism: string | null;
  mechanism_exclusive: boolean;
  endorsement: string | null;
  user_feedback: string | null;
  unique_selling: string | null;
  awards: string | null;
  efficacy_proof: string | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface QianchuanProductsPage {
  items: QianchuanProduct[];
  pagination: { page: number; page_size: number; total: number; total_pages: number };
}

// 对标账号
export interface KolBenchmark {
  id: number;
  kol_id: number;
  account_name: string;
  account_type: 'content' | 'livestream';
  description: string | null;
  sort_order: number;
}

// 首页聚合
export interface WorkspaceDashboardData {
  kol: { id: number; name: string; avatar_url: string | null; category: string | null };
  benchmarks: { content: KolBenchmark[]; livestream: KolBenchmark[] };
  active_products: QianchuanProduct[];
}

// 人物档案
export interface PersonaDetails {
  kol_id: number;
  background: string | null;
  experience: string | null;
  relationships: string | null;
  unique_story: string | null;
  extra_notes: string | null;
  updated_at: string | null;
}

// 工作台 Tab 枚举
export type WorkspaceTab =
  | 'dashboard'
  | 'persona'            // Sprint 19
  | 'products'
  | 'qianchuan-writer'   // Sprint 19
  | 'seeding-writer'     // Sprint 19
  | 'persona-writer'     // Sprint 19
  | 'livestream-writer'  // Sprint 19
  | 'livestream-review'  // Sprint 19
  | 'values-writer'      // Sprint 20
  | 'script-review'      // Sprint 21
  | 'film-review'        // Sprint 23
  | 'retrospective'      // Sprint 22
  | 'references';        // Sprint 19
