import type { Page } from '@playwright/test';

/**
 * Auth helper：走真实 UI 登录流程。
 *
 * 之前尝试 storageState / addInitScript / evaluate 注入，
 * 在 channel:'chrome' + zustand 模块作用域 init 时序下都不稳定。
 * UI 登录最稳——React app 走正常流程，zustand store 状态正确，
 * ProtectedRoute 验证 getMe 必通过。
 */

const TOKEN_KEY = 'mcn_token';
const API_BASE = 'http://localhost:8000';
const USERNAME = 'admin';
const PASSWORD = 'Admin@123456';

/**
 * 在 page 上完成 UI 登录。调用方在 loginAsAdmin 之后 goto 目标页。
 *
 * 用法：
 * ```ts
 * test('xxx', async ({ page }) => {
 *   await loginAsAdmin(page);
 *   await page.goto('/workspace/seeding-writer');
 *   // ...
 * });
 * ```
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  // 输入账号密码（placeholder 来自 LoginPage）
  await page.locator('input[placeholder="请输入账号"]').fill(USERNAME);
  await page.locator('input[placeholder="请输入密码"]').fill(PASSWORD);

  // 点「登录」按钮（AntD 中文字间加空格 → 正则）
  const loginBtn = page.getByRole('button', { name: /^登\s*录$/ }).first();
  await loginBtn.click();

  // 等待跳转到非 /login 页面（ProtectedRoute 验证通过）
  await page.waitForURL(/^(?!.*\/login).+$/, { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
}

/** 用 API 拿一个 token（用于直接 evaluate 调 API 场景，非 React auth 流程）。 */
export async function fetchAdminToken(): Promise<string> {
  const resp = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  if (!resp.ok) {
    throw new Error(`admin login failed: ${resp.status}`);
  }
  const body = await resp.json();
  return body.data.access_token as string;
}

// 兼容性导出（旧代码可能 import TOKEN_KEY）
export { TOKEN_KEY };
