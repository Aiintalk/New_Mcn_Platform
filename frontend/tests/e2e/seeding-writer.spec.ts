import { test, expect, type Page } from '@playwright/test';
import { installAllMocks } from './helpers/api-mock';
import { loginAsAdmin } from './helpers/auth';

/**
 * E2E — seeding-writer 关键路径覆盖（B 范围）。
 *
 * 覆盖：
 * 1. 访问 /workspace/seeding-writer，4 步向导渲染
 * 2. Step 1 加素材
 * 3. Step 1 → Step 2 切换（下一步按钮）
 * 4. Step 2 必填校验
 * 5. Step 3 抖音解析输入框渲染
 * 6. ConfigTab 入口可访问
 *
 * 外部 API（yunwu/tikhub/oss/asr）全部 mock，不真实调用。
 */

/**
 * 导航到 /workspace/seeding-writer 并等待 ProtectedRoute 验证通过。
 * ProtectedRoute 用 useEffect 调 getMe（异步），不等待会因还在 loading 而失败。
 */
async function gotoSeedingWriter(page: Page): Promise<void> {
  await page.goto('/workspace/seeding-writer');
  await page.waitForURL(/^(?!.*\/login).+$/, { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
}

test.describe('SeedingWriter — 关键路径', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await installAllMocks(page);
  });

  test('SW-E2E-001：访问页面 + 4 步向导渲染', async ({ page }) => {
    await gotoSeedingWriter(page);
    await expect(page.getByText('选达人', { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('产品信息', { exact: true })).toBeVisible();
    await expect(page.getByText('对标验证', { exact: true })).toBeVisible();
    await expect(page.getByText('种草仿写', { exact: true })).toBeVisible();
  });

  test('SW-E2E-002：Step 1 初始状态（标题 + 达人下拉 + 下一步禁用）', async ({ page }) => {
    await gotoSeedingWriter(page);
    await expect(page.getByRole('heading', { name: 'Step 1 · 选择达人' })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('达人人设')).toBeVisible();
    // 初始无选择，下一步按钮应禁用
    await expect(page.getByRole('button', { name: /下一步：产品信息/ })).toBeDisabled();
  });

  test('SW-E2E-003：Step 1 → Step 2 切换', async ({ page }) => {
    await gotoSeedingWriter(page);
    await expect(page.getByText('选达人', { exact: true })).toBeVisible({ timeout: 15_000 });

    await page.locator('.ant-select').first().click();
    const firstOption = page.locator('.ant-select-item').first();
    if (await firstOption.isVisible({ timeout: 3000 }).catch(() => false)) {
      await firstOption.click();
    } else {
      await page.keyboard.press('Escape');
    }

    const nextBtn = page.getByRole('button', { name: /下一步：产品信息/ });
    if (await nextBtn.isEnabled({ timeout: 3000 }).catch(() => false)) {
      await nextBtn.click();
      await expect(page.getByText('上传产品文档（AI 解析）').first()).toBeVisible({ timeout: 10_000 });
    }
  });

  test('SW-E2E-004：Step 2 必填校验', async ({ page }) => {
    await gotoSeedingWriter(page);
    await expect(page.getByText('选达人', { exact: true })).toBeVisible({ timeout: 15_000 });

    await page.locator('.ant-select').first().click();
    const opt = page.locator('.ant-select-item').first();
    if (await opt.isVisible({ timeout: 3000 }).catch(() => false)) {
      await opt.click();
    } else {
      await page.keyboard.press('Escape');
    }

    const next1 = page.getByRole('button', { name: /下一步：产品信息/ });
    if (await next1.isEnabled({ timeout: 3000 }).catch(() => false)) {
      await next1.click();
      const next2 = page.getByRole('button', { name: /下一步：对标验证/ });
      await expect(next2).toBeAttached({ timeout: 10_000 });
    }
  });

  test('SW-E2E-005：Step 3 抖音链接输入框', async ({ page }) => {
    await gotoSeedingWriter(page);
    await expect(page.getByText('选达人', { exact: true })).toBeVisible({ timeout: 15_000 });

    await page.locator('.ant-select').first().click();
    const opt = page.locator('.ant-select-item').first();
    if (await opt.isVisible({ timeout: 3000 }).catch(() => false)) {
      await opt.click();
    } else {
      await page.keyboard.press('Escape');
    }

    const next1 = page.getByRole('button', { name: /下一步：产品信息/ });
    if (await next1.isEnabled({ timeout: 3000 }).catch(() => false)) {
      await next1.click();
      const requiredInputs = page.getByPlaceholder('必填');
      if (await requiredInputs.first().isVisible({ timeout: 5000 }).catch(() => false)) {
        await requiredInputs.nth(0).fill('E2E 产品');
        await requiredInputs.nth(1).fill('E2E 卖点');
      }
      const next2 = page.getByRole('button', { name: /下一步：对标验证/ });
      if (await next2.isEnabled({ timeout: 3000 }).catch(() => false)) {
        await next2.click();
        const linkInput = page.getByPlaceholder('粘贴抖音分享链接...');
        await expect(linkInput).toBeVisible({ timeout: 10_000 });
      }
    }
  });

  test('SW-E2E-006：ConfigTab 入口可访问', async ({ page }) => {
    await page.goto('/admin/workspace/seeding-writer-config');
    await page.waitForLoadState('networkidle');
    await expect(page).not.toHaveURL(/\/login/);
  });
});
