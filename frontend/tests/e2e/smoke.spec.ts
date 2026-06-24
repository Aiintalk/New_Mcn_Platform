import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers/auth';

/**
 * E2E smoke 测试 — 验证基础设施可跑通。
 *
 * 覆盖：
 * 1. 前端 dev server 启动 + 首页可访问
 * 2. /login 路由可访问
 * 3. admin 登录后能跳转到首页（不被 ProtectedRoute 弹回 /login）
 */
test.describe('Smoke — 基础设施验证', () => {
  test('首页可访问', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\//);
  });

  test('/login 路由可访问', async ({ page }) => {
    await page.goto('/login');
    await expect(page).toHaveURL(/\/login/);
  });

  test('admin 登录后可访问受保护页面', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/');
    // 登录后应跳到 / 或 /workspace（不是 /login）
    await page.waitForURL(/^(?!.*\/login).+$/, { timeout: 15_000 });
    await expect(page).not.toHaveURL(/\/login/);
  });
});
