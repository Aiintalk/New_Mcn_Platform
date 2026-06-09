import { message } from 'antd';
import { useAuthStore } from '../store/authStore';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export interface ApiError {
  code: string;
  message: string;
}

function buildHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(res: Response): Promise<T> {
  let body: { success: boolean; code: string; message: string; data: T | null };
  try {
    body = await res.json();
  } catch {
    throw new Error('Invalid JSON response from server');
  }

  if (!body.success) {
    const { code, message: msg } = body;

    if (code === 'AUTH_TOKEN_EXPIRED' || code === 'AUTH_TOKEN_MISSING' || res.status === 401) {
      useAuthStore.getState().clearAuth();
      window.location.href = '/login';
      throw Object.assign(new Error(msg), { code });
    }

    if (code === 'AUTH_FORCE_CHANGE_PASSWORD') {
      window.location.href = '/change-password';
      throw Object.assign(new Error(msg), { code });
    }

    if (code === 'PERMISSION_DENIED') {
      message.error('无权限访问');
      throw Object.assign(new Error(msg), { code });
    }

    throw Object.assign(new Error(msg), { code });
  }

  return body.data as T;
}

export async function get<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): Promise<T> {
  let url = `${BASE_URL}${path}`;
  if (params) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') sp.append(k, String(v));
    }
    const qs = sp.toString();
    if (qs) url += `?${qs}`;
  }
  const res = await fetch(url, { method: 'GET', headers: buildHeaders() });
  return handleResponse<T>(res);
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: buildHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

export async function patch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PATCH',
    headers: buildHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

export async function put<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PUT',
    headers: buildHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  });
  return handleResponse<T>(res);
}
