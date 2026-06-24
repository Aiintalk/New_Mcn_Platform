import { get, post, put, del } from './request';
import type {
  PersonaOption,
  Reference,
  Product,
  ProductsPage,
  ParsedProductDocument,
  VideoInfo,
  SeedingWriterConfig,
  OutputsPage,
  CreateReferenceRequest,
  ImportReferenceRequest,
  CreateProductRequest,
  UpdateProductRequest,
  ExtractSellingPointsRequest,
  AnalyzeStructureRequest,
  AiRecommendRequest,
  SeedingChatRequest,
  SaveOutputRequest,
  ExportWordRequest,
} from '../types/seedingWriter';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// 运营端 20 个接口
// ---------------------------------------------------------------------------

// ===== Step 1: 达人 + 素材库 (5) =====

/** Step 1.1：获取有人设的达人列表 */
export const getPersonas = () =>
  get<PersonaOption[]>('/api/tools/seeding-writer/kols/personas');

/** Step 1.2：获取某达人的素材列表（达人维度共享） */
export function getReferences(kolId: number): Promise<Reference[]> {
  return get<Reference[]>('/api/tools/seeding-writer/references', {
    kol_id: kolId,
  });
}

/** Step 1.2a：新增素材（粘贴文本） */
export function createReference(body: CreateReferenceRequest): Promise<{ id: number }> {
  return post<{ id: number }>('/api/tools/seeding-writer/references', body);
}

/** Step 1.2b：抖音链接导入素材（同步阻塞） */
export function importReferenceFromDouyin(
  body: ImportReferenceRequest,
): Promise<{ id: number; title: string; content: string }> {
  return post('/api/tools/seeding-writer/references/import-from-douyin', body);
}

/** Step 1.2c：删除素材 */
export function deleteReference(id: number): Promise<{ success: boolean }> {
  return del<{ success: boolean }>(`/api/tools/seeding-writer/references/${id}`);
}

// ===== Step 2: 产品信息 (6) =====

/** Step 2.1：产品库列表（公司共享，分页） */
export function getProducts(
  page: number = 1,
  pageSize: number = 20,
  search?: string,
): Promise<ProductsPage> {
  return get<ProductsPage>('/api/tools/seeding-writer/products', {
    page,
    page_size: pageSize,
    search,
  });
}

/** Step 2.1a：新建产品 */
export function createProduct(body: CreateProductRequest): Promise<{ id: number }> {
  return post<{ id: number }>('/api/tools/seeding-writer/products', body);
}

/** Step 2.1b：更新产品 */
export function updateProduct(
  id: number,
  body: UpdateProductRequest,
): Promise<{ success: boolean }> {
  return put<{ success: boolean }>(`/api/tools/seeding-writer/products/${id}`, body);
}

/** Step 2.1c：软删产品 */
export function deleteProduct(id: number): Promise<{ success: boolean }> {
  return del<{ success: boolean }>(`/api/tools/seeding-writer/products/${id}`);
}

/** Step 2.1d：上传产品文档 AI 解析（multipart 例外不走 request.ts） */
export async function parseProductDocument(
  files: File[],
): Promise<ParsedProductDocument> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // multipart 例外：FormData 上传不走 request.ts
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  const resp = await fetch(`${BASE_URL}/api/tools/seeding-writer/products/parse-document`, {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: fd,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `解析失败: ${resp.status}`);
  }
  const body = await resp.json();
  if (!body.success) {
    throw new Error(body.message ?? '解析失败');
  }
  return body.data as ParsedProductDocument;
}

/** Step 2.2：AI 卖点讨论（流式，sp_system_prompt） */
export async function extractSellingPointsStream(
  body: ExtractSellingPointsRequest,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(
    `${BASE_URL}/api/tools/seeding-writer/products/extract-selling-points`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `卖点讨论失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

// ===== Step 3: 对标验证 (4) =====

/** Step 3.1：抖音链接解析 */
export function fetchVideo(share_url: string): Promise<VideoInfo> {
  return post<VideoInfo>('/api/tools/seeding-writer/fetch-video', { share_url });
}

/** Step 3.2a：提交 ASR 任务 */
export function submitTranscribe(play_url: string): Promise<{ task_id: string }> {
  return post<{ task_id: string }>('/api/tools/seeding-writer/transcribe/submit', {
    play_url,
  });
}

/** Step 3.2b：轮询 ASR 结果 */
export function pollTranscribe(
  task_id: string,
): Promise<{ status: string; text?: string }> {
  return post<{ status: string; text?: string }>(
    '/api/tools/seeding-writer/transcribe/poll',
    { task_id },
  );
}

/** Step 3.4：结构拆解（流式，light 模型） */
export async function analyzeStructureStream(
  body: AnalyzeStructureRequest,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/tools/seeding-writer/analyze-structure`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `结构拆解失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

// ===== Step 4: 种草仿写 (4) =====

/** Step 4.1：AI 推荐种草角度（流式，light 模型） */
export async function aiRecommendStream(
  body: AiRecommendRequest,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/tools/seeding-writer/ai-recommend`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `AI 推荐失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

/** Step 4.2/4.3/4.4：写作 + 字数校验 + 多轮迭代（流式，heavy 模型） */
export async function chatStream(
  body: SeedingChatRequest,
  onChunk: (full: string) => void,
): Promise<string> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  // SSE 流式：resp.body.getReader()（例外不走 request.ts）
  const resp = await fetch(`${BASE_URL}/api/tools/seeding-writer/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `生成失败: ${resp.status}`);
  }
  return readPlainStream(resp, onChunk);
}

/** Step 4.5：保存产出 */
export function saveOutput(body: SaveOutputRequest): Promise<{ output_id: number }> {
  return post<{ output_id: number }>('/api/tools/seeding-writer/save-output', body);
}

/** Step 4.6b：导出 Word（Blob 例外） */
export async function exportWord(body: ExportWordRequest): Promise<Blob> {
  const { useAuthStore } = await import('../store/authStore');
  const token = useAuthStore.getState().token;
  const resp = await fetch(`${BASE_URL}/api/tools/seeding-writer/export-word`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err?.detail?.message ?? `导出失败: ${resp.status}`);
  }
  return resp.blob();
}

/** 历史记录列表（账号隔离） */
export function getOutputs(page: number, pageSize: number = 20): Promise<OutputsPage> {
  return get<OutputsPage>('/api/tools/seeding-writer/outputs', {
    page,
    page_size: pageSize,
  });
}

// ---------------------------------------------------------------------------
// 管理端 2 个接口
// ---------------------------------------------------------------------------

/** 管理端：获取配置列表 */
export const getConfigs = () =>
  get<SeedingWriterConfig[]>('/api/admin/seeding-writer/configs');

/** 管理端：更新配置（6 Prompt + 2 模型 + 启用） */
export function updateConfig(
  configKey: string,
  payload: {
    sp_system_prompt?: string | null;
    parse_product_prompt?: string | null;
    structure_analysis_prompt?: string | null;
    ai_recommend_prompt?: string | null;
    writing_prompt?: string | null;
    iteration_prompt?: string | null;
    light_model_id?: number | null;
    heavy_model_id?: number | null;
    is_active?: boolean;
  },
): Promise<{ config_key: string }> {
  return put<{ config_key: string }>(
    `/api/admin/seeding-writer/configs/${configKey}`,
    payload,
  );
}

// ---------------------------------------------------------------------------
// 内部 helper
// ---------------------------------------------------------------------------

/** 读取 text/plain 流，累计拼接后通过 onChunk 回调 */
async function readPlainStream(
  resp: Response,
  onChunk: (full: string) => void,
): Promise<string> {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let full = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    onChunk(full);
  }
  return full;
}
