export type CredentialStatus = 'enabled' | 'disabled' | 'cooldown';

export interface ServiceCredential {
  id: number;
  provider: string;
  label: string;
  secret_tail: string;
  status: CredentialStatus;
  weight: number;
  quota_limit: number | null;
  quota_used: number | null;
  fail_count: number;
  cooldown_until: string | null;
  config: Record<string, unknown> | null;
  last_tested_at: string | null;
  last_latency_ms: number | null;
  created_at: string;
}

export interface CreateCredentialRequest {
  provider: string;
  label: string;
  api_key: string;
  weight: number;
  quota_limit?: number;
  config?: Record<string, unknown>;
}

export interface UpdateCredentialRequest {
  label?: string;
  status?: string;
  weight?: number;
  quota_limit?: number;
  config?: Record<string, unknown>;
  /** 提供则同步轮换 secret_enc + secret_tail（密钥轮换） */
  api_key?: string;
}

/** POST /api/admin/config/credentials/{id}/test 响应 data */
export interface OssTestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  /** status=ok 时的 bucket 元数据 */
  bucket?: string;
  location?: string;
  creation_date?: string;
  /** status=error 时的异常信息（前 200 字符） */
  error?: string;
}
