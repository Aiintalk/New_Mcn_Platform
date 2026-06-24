import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E 配置（Sprint 16 v3 引入）。
 *
 * 约定：
 * - 前端 dev server 由 webServer 自动启动（端口 5175，与 PM 记忆一致）
 * - 后端 API（uvicorn :8000）需要手动启动，测试前请确认在跑
 * - 浏览器：仅 Chromium（关键路径覆盖，不做跨浏览器）
 * - 外部 API（yunwu AI / tikhub / oss / asr）通过 page.route() mock，不真实调用
 * - workers=1 串行执行，避免并发污染数据库
 *
 * 跑测试前：
 *   1. cd backend && uvicorn app.main:app --reload --port 8000
 *   2. cd frontend && npx playwright test
 */
export default defineConfig({
  testDir: './tests/e2e',
  outputDir: './test-results',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputDir: 'playwright-report', open: 'never' }],
  ],
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: 'http://localhost:5175',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // 用系统 Chrome（用户已装）替代 Playwright 自带 chromium
        // 避免 Playwright CDN 国内下载困难；如需切回自带 chromium，删掉 channel 字段
        channel: 'chrome',
      },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5175',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
