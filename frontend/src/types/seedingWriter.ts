// Types for 种草内容仿写（seeding-writer）

/** Step 1 达人列表项（与 persona-writer 共享同结构）*/
export interface PersonaOption {
  id: number;
  name: string;
  soul_preview: string;
  creator_name: string;
}

/** 素材库条目 */
export interface Reference {
  id: number;
  kol_id: number | null;
  title: string;
  content: string;
  type: string | null;
  source: string | null;
  likes: number | null;
  douyin_url: string | null;
  created_at: string | null;
}

/** Step 2 产品信息（表单可编辑字段）*/
export interface ProductInfo {
  name: string;
  category: string;
  price: string;
  targetAudience: string;
  sellingPoints: string;
  scenario: string;
  medicalAestheticAnchor: string;
}

/** 产品库条目（后端返回结构）*/
export interface Product {
  id: number;
  name: string;
  category: string | null;
  price: string | null;
  selling_points: string | null;
  target_audience: string | null;
  scenario: string | null;
  medical_aesthetic_anchor: string | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 产品库分页响应 */
export interface ProductsPage {
  items: Product[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

/** 文档解析返回（POST /products/parse-document）*/
export interface ParsedProductDocument {
  name: string;
  category: string;
  price: string;
  sellingPoints: string;
  targetAudience: string;
  scenario: string;
  medicalAestheticAnchor: string;
  _rawText: string;
}

/** chat / 卖点讨论消息 */
export interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
}

/** Step 3 fetch-video 返回 */
export interface VideoInfo {
  title: string;
  digg_count: number;
  aweme_id: string;
  play_url: string;
}

/** 管理端配置项（6 Prompt + 2 模型 + 启用）*/
export interface SeedingWriterConfig {
  id: number;
  config_key: string;
  sp_system_prompt: string | null;
  parse_product_prompt: string | null;
  structure_analysis_prompt: string | null;
  ai_recommend_prompt: string | null;
  writing_prompt: string | null;
  iteration_prompt: string | null;
  light_model_id: number | null;
  heavy_model_id: number | null;
  is_active: boolean;
  updated_at: string | null;
}

/** 历史记录项 */
export interface SeedingWriterOutput {
  id: number;
  title: string;
  content: string;
  word_count: number;
  task_id: number | null;
  created_at: string | null;
}

/** 历史记录分页响应 */
export interface OutputsPage {
  items: SeedingWriterOutput[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

/** POST /references 请求体 */
export interface CreateReferenceRequest {
  kol_id: number;
  title: string;
  content: string;
  type?: string;
  source?: string;
  likes?: number;
}

/** POST /references/import-from-douyin 请求体 */
export interface ImportReferenceRequest {
  kol_id: number;
  share_url: string;
  type: string;
}

/** POST /products 请求体 */
export interface CreateProductRequest {
  name: string;
  category?: string;
  price?: string;
  selling_points?: string;
  target_audience?: string;
  scenario?: string;
  medical_aesthetic_anchor?: string;
}

/** PUT /products/{id} 请求体 */
export interface UpdateProductRequest extends CreateProductRequest {}

/** POST /products/extract-selling-points 请求体 */
export interface ExtractSellingPointsRequest {
  raw_text: string;
  preliminary_info: ProductInfo;
}

/** POST /analyze-structure 请求体 */
export interface AnalyzeStructureRequest {
  transcript: string;
}

/** POST /ai-recommend 请求体 */
export interface AiRecommendRequest {
  persona_id: number;
  product_id: number | null;
  reference_ids: number[];
  transcript: string;
}

/** POST /chat 请求体 */
export interface SeedingChatRequest {
  scene: 'writing' | 'iteration';
  persona_id: number;
  product_id: number | null;
  reference_ids: number[];
  transcript?: string;
  structure_analysis?: string;
  topic?: string;
  messages: ChatMsg[];
  create_job?: boolean;
}

/** POST /save-output 请求体 */
export interface SaveOutputRequest {
  content: string;
  title?: string;
  task_id?: number | null;
  topic?: string | null;
  transcript_digest?: string | null;
}

/** POST /export-word 请求体 */
export interface ExportWordRequest {
  content: string;
  filename?: string;
}
