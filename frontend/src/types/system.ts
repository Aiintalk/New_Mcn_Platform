export interface AITestResult {
  status: 'ok' | 'error';
  model?: string;
  latency_ms: number;
  reply?: string;
  error?: string;
}

export interface ServiceTestResult {
  status: 'ok' | 'error';
  latency_ms: number;
  error?: string;
  [key: string]: unknown;
}

export interface HealthData {
  status: string;
  service: string;
  database: string;
  time: string;
}
