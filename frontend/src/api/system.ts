import { get, post } from './request';
import type { HealthData, AITestResult, ServiceTestResult } from '../types/system';

export async function getHealth(): Promise<HealthData> {
  return get<HealthData>('/api/health');
}

export async function testAIConnection(): Promise<AITestResult> {
  return post<AITestResult>('/api/admin/system/ai-test');
}

export async function testTikHubConnection(): Promise<ServiceTestResult> {
  return post<ServiceTestResult>('/api/admin/system/tikhub-test');
}
