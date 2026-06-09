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
  created_at: string;
}

export interface CreateCredentialRequest {
  provider: string;
  label: string;
  secret: string;
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
}
