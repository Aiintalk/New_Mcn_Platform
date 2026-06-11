import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the request module
const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDel = vi.fn();

vi.mock('../../../api/request', () => ({
  get: (...args: unknown[]) => mockGet(...args),
  post: (...args: unknown[]) => mockPost(...args),
  patch: (...args: unknown[]) => mockPatch(...args),
  del: (...args: unknown[]) => mockDel(...args),
  put: vi.fn(),
}));

import {
  checkUsername,
  getUsers,
  createUser,
  updateUser,
  resetPassword,
  enableUser,
  disableUser,
  deleteUser,
} from '../../../api/users';

describe('users API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- checkUsername ---

  it('checkUsername calls GET /api/admin/users/check-username with username param', async () => {
    mockGet.mockResolvedValue({ available: true });

    const result = await checkUsername('testuser');

    expect(result).toEqual({ available: true });
    expect(mockGet).toHaveBeenCalledWith(
      '/api/admin/users/check-username',
      { username: 'testuser' },
    );
    expect(mockGet).toHaveBeenCalledTimes(1);
  });

  // --- getUsers ---

  it('getUsers calls GET /api/admin/users without params', async () => {
    const pagedData = { items: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(pagedData);

    const result = await getUsers();

    expect(result).toEqual(pagedData);
    expect(mockGet).toHaveBeenCalledWith('/api/admin/users', undefined);
  });

  it('getUsers passes pagination and filter params', async () => {
    const pagedData = { items: [], pagination: { page: 1, page_size: 10, total: 0, total_pages: 0 } };
    mockGet.mockResolvedValue(pagedData);

    const params = { page: 2, page_size: 10, keyword: 'admin', status: 'enabled', role: 'admin' };
    const result = await getUsers(params);

    expect(result).toEqual(pagedData);
    expect(mockGet).toHaveBeenCalledWith('/api/admin/users', params);
  });

  // --- createUser ---

  it('createUser calls POST /api/admin/users with user data', async () => {
    const createResponse = {
      id: 1,
      username: 'newuser',
      real_name: 'New User',
      role: 'operator' as const,
      status: 'enabled',
      initial_password: 'abc123',
    };
    mockPost.mockResolvedValue(createResponse);

    const data = { username: 'newuser', real_name: 'New User', role: 'operator' as const };
    const result = await createUser(data);

    expect(result).toEqual(createResponse);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/users', data);
  });

  it('createUser sends password when provided', async () => {
    const createResponse = {
      id: 2,
      username: 'pwuser',
      real_name: 'PW User',
      role: 'admin' as const,
      status: 'enabled',
      initial_password: 'custom',
    };
    mockPost.mockResolvedValue(createResponse);

    const data = { username: 'pwuser', real_name: 'PW User', role: 'admin' as const, password: 'custom' };
    const result = await createUser(data);

    expect(result).toEqual(createResponse);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/users', data);
  });

  // --- updateUser ---

  it('updateUser calls PATCH /api/admin/users/:id with update data', async () => {
    const updatedUser = { id: 1, username: 'user1', real_name: 'Updated', role: 'operator', status: 'enabled', must_change_password: false, last_login_at: null };
    mockPatch.mockResolvedValue(updatedUser);

    const data = { real_name: 'Updated' };
    const result = await updateUser(1, data);

    expect(result).toEqual(updatedUser);
    expect(mockPatch).toHaveBeenCalledWith('/api/admin/users/1', data);
  });

  it('updateUser uses the correct id in URL', async () => {
    mockPatch.mockResolvedValue({});

    await updateUser(42, { status: 'disabled' });

    expect(mockPatch).toHaveBeenCalledWith('/api/admin/users/42', { status: 'disabled' });
  });

  // --- resetPassword ---

  it('resetPassword calls POST /api/admin/users/:id/reset-password', async () => {
    const resetResponse = { initial_password: 'newpass123' };
    mockPost.mockResolvedValue(resetResponse);

    const result = await resetPassword(5);

    expect(result).toEqual(resetResponse);
    expect(mockPost).toHaveBeenCalledWith('/api/admin/users/5/reset-password');
  });

  // --- enableUser ---

  it('enableUser calls POST /api/admin/users/:id/enable', async () => {
    mockPost.mockResolvedValue(null);

    await enableUser(3);

    expect(mockPost).toHaveBeenCalledWith('/api/admin/users/3/enable');
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  // --- disableUser ---

  it('disableUser calls POST /api/admin/users/:id/disable', async () => {
    mockPost.mockResolvedValue(null);

    await disableUser(3);

    expect(mockPost).toHaveBeenCalledWith('/api/admin/users/3/disable');
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  // --- deleteUser ---

  it('deleteUser calls DELETE /api/admin/users/:id', async () => {
    mockDel.mockResolvedValue(null);

    await deleteUser(7);

    expect(mockDel).toHaveBeenCalledWith('/api/admin/users/7');
    expect(mockDel).toHaveBeenCalledTimes(1);
  });

  // --- error propagation ---

  it('getUsers propagates errors from request layer', async () => {
    mockGet.mockRejectedValue(new Error('Server error'));

    await expect(getUsers()).rejects.toThrow('Server error');
  });

  it('createUser propagates errors from request layer', async () => {
    mockPost.mockRejectedValue(new Error('Username already exists'));

    await expect(createUser({ username: 'dup', real_name: 'Dup', role: 'operator' }))
      .rejects.toThrow('Username already exists');
  });

  it('deleteUser propagates errors from request layer', async () => {
    mockDel.mockRejectedValue(new Error('Not found'));

    await expect(deleteUser(999)).rejects.toThrow('Not found');
  });
});
