import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock authStore before importing request
const mockClearAuth = vi.fn();
let mockToken: string | null = null;

vi.mock('../../../store/authStore', () => ({
  useAuthStore: {
    getState: () => ({ token: mockToken, clearAuth: mockClearAuth }),
  },
}));

// Mock antd message
vi.mock('antd', () => ({
  message: { error: vi.fn() },
}));

import { get, post, patch, put, del } from '../../../api/request';

const BASE_URL = 'http://localhost:8000';

function mockFetchResponse(body: unknown, status = 200) {
  return vi.fn(() =>
    Promise.resolve({
      status,
      json: () => Promise.resolve(body),
    } as Response)
  );
}

describe('request.ts', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockToken = null;
    mockClearAuth.mockClear();
    // Prevent real navigation
    Object.defineProperty(window, 'location', {
      value: { href: '' },
      writable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // --- get ---

  it('get sends request with auth header when token exists', async () => {
    mockToken = 'my-jwt';
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: { id: 1 },
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    const result = await get('/api/test');
    expect(result).toEqual({ id: 1 });
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/test`,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({ Authorization: 'Bearer my-jwt' }),
      })
    );
  });

  it('get appends query params correctly', async () => {
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: [],
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    await get('/api/items', { page: 1, page_size: 10 });
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/items?page=1&page_size=10`,
      expect.any(Object)
    );
  });

  it('get skips undefined and empty string params', async () => {
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: [],
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    await get('/api/items', { page: 1, search: '', filter: undefined });
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/items?page=1`,
      expect.any(Object)
    );
  });

  // --- post ---

  it('post sends JSON body', async () => {
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: { id: 2 },
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    const result = await post('/api/create', { name: 'test' });
    expect(result).toEqual({ id: 2 });
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/create`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'test' }),
      })
    );
  });

  // --- handleResponse error paths ---

  it('handleResponse AUTH_TOKEN_EXPIRED clears auth and redirects to login', async () => {
    mockToken = 'expired';

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      mockFetchResponse({
        success: false,
        code: 'AUTH_TOKEN_EXPIRED',
        message: 'Token expired',
        data: null,
      })
    );

    await expect(get('/api/test')).rejects.toThrow('Token expired');
    expect(mockClearAuth).toHaveBeenCalled();
    expect(window.location.href).toBe('/login');
  });

  it('handleResponse AUTH_TOKEN_MISSING clears auth and redirects to login', async () => {
    mockToken = 'some-token';

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      mockFetchResponse({
        success: false,
        code: 'AUTH_TOKEN_MISSING',
        message: 'Missing',
        data: null,
      })
    );

    await expect(get('/api/test')).rejects.toThrow('Missing');
    expect(mockClearAuth).toHaveBeenCalled();
    expect(window.location.href).toBe('/login');
  });

  it('handleResponse AUTH_FORCE_CHANGE_PASSWORD redirects to change-password', async () => {
    mockToken = 'token';

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      mockFetchResponse({
        success: false,
        code: 'AUTH_FORCE_CHANGE_PASSWORD',
        message: 'Must change password',
        data: null,
      })
    );

    await expect(get('/api/test')).rejects.toThrow('Must change password');
    expect(window.location.href).toBe('/change-password');
  });

  it('handleResponse PERMISSION_DENIED shows error message', async () => {
    const { message } = await import('antd');

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      mockFetchResponse({
        success: false,
        code: 'PERMISSION_DENIED',
        message: 'No access',
        data: null,
      })
    );

    await expect(get('/api/test')).rejects.toThrow('No access');
    expect(message.error).toHaveBeenCalledWith('无权限访问');
  });

  it('handleResponse generic error throws with code', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      mockFetchResponse({
        success: false,
        code: 'VALIDATION_ERROR',
        message: 'Invalid input',
        data: null,
      })
    );

    await expect(get('/api/test')).rejects.toThrow('Invalid input');
  });

  // --- HTTP 401 status ---

  it('handleResponse HTTP 401 status triggers auth clear', async () => {
    mockToken = 'token';

    vi.spyOn(globalThis, 'fetch').mockImplementation(
      mockFetchResponse({
        success: false,
        code: 'OTHER_ERROR',
        message: 'Unauthorized',
        data: null,
      }, 401)
    );

    await expect(get('/api/test')).rejects.toThrow('Unauthorized');
    expect(mockClearAuth).toHaveBeenCalled();
    expect(window.location.href).toBe('/login');
  });

  // --- patch / put / del ---

  it('patch sends PATCH request with body', async () => {
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: { ok: true },
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    await patch('/api/update', { status: 'enabled' });
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/update`,
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ status: 'enabled' }) })
    );
  });

  it('put sends PUT request with body', async () => {
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: { ok: true },
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    await put('/api/replace', { name: 'new' });
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/replace`,
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ name: 'new' }) })
    );
  });

  it('del sends DELETE request without body', async () => {
    const fetchMock = mockFetchResponse({
      success: true,
      code: '',
      message: '',
      data: null,
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation(fetchMock);

    await del('/api/item/1');
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE_URL}/api/item/1`,
      expect.objectContaining({ method: 'DELETE' })
    );
  });
});
