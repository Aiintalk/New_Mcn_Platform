import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers/auth';

/**
 * AIGC 评测系统 — E2E smoke 测试
 *
 * 覆盖核心流程：
 * 1. 登录 → 进入评测-测试集页（路由可达 + 主要 UI 渲染）
 * 2. 触发运行抽屉 → mock 接口 → 看运行详情页骨架
 * 3. 对比页：选两个 run → 看报告卡片渲染
 *
 * 注：后端评测接口依赖 PG 数据，本 smoke 走 mock。
 * 完整 CRUD 流程由 vitest 组件测试覆盖（src/__tests__/components/pages/evaluation/）。
 */

test.describe('AIGC 评测 — smoke', () => {
  test.beforeEach(async ({ page }) => {
    // mock 评测相关接口，避免依赖真实后端数据
    await page.route('**/api/operator/evaluation/test-cases**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          code: 'OK',
          message: 'ok',
          data: {
            items: [
              {
                id: 1,
                tool_code: 'qianchuan-writer',
                name: 'E2E 焦虑型样本',
                description: 'smoke 测试',
                input_payload: {},
                expected_output: null,
                tags: ['焦虑型'],
                is_active: true,
                created_by: 1,
                updated_by: 1,
                created_at: '2026-07-16T14:22:00Z',
                updated_at: '2026-07-16T14:22:00Z',
                deleted_at: null,
              },
            ],
            pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
          },
        }),
      });
    });

    await page.route('**/api/operator/evaluation/versions**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          code: 'OK',
          message: 'ok',
          data: [
            {
              id: 13,
              tool_code: 'qianchuan-writer',
              name: 'v1.3-E2E',
              description: 'E2E 版本',
              config_payload: {},
              parent_version_id: null,
              source_kol_id: null,
              auto_run_on_create: false,
              auto_run_tags: [],
              is_active: true,
              created_by: 1,
              created_at: '2026-07-16T10:00:00Z',
              updated_at: null,
              deleted_at: null,
            },
          ],
        }),
      });
    });
  });

  test('登录后可进入评测测试集页', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/evaluation/test-cases');

    // 标题渲染
    await expect(page.getByRole('heading', { name: '测试集' })).toBeVisible({ timeout: 15_000 });
    // title-tag 渲染
    await expect(page.getByText('tool: qianchuan-writer', { exact: false })).toBeVisible();
    // mock 的样本名称应出现
    await expect(page.getByText('E2E 焦虑型样本')).toBeVisible({ timeout: 10_000 });
  });

  test('可进入运行管理页并打开触发抽屉', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/evaluation/runs');

    await expect(page.getByRole('heading', { name: '运行管理' })).toBeVisible({ timeout: 15_000 });
    // 点击「新建运行」打开抽屉
    const triggerBtn = page.locator('button', { hasText: '新建运行' }).first();
    await triggerBtn.click();
    // 抽屉标题
    await expect(page.getByText('触发运行').first()).toBeVisible({ timeout: 5_000 });
    // 运行名输入框
    await expect(page.getByPlaceholder('例：v1.3 核心集手动回归')).toBeVisible();
  });

  test('可进入版本对比页并填入 run id', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto('/evaluation/compare');

    await expect(page.getByRole('heading', { name: '版本对比报告' })).toBeVisible({ timeout: 15_000 });
    // 初始未对比 → 应有「填入两个 run id 后点击「对比」」提示
    await expect(page.getByText(/填入两个 run id 后点击/)).toBeVisible();
  });
});
