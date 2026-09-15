import { test, expect } from '../../../admin_web/frontend/node_modules/@playwright/test/index.mjs';

// Run against a disposable catalog + local companion; provider calls are mocked.
test('paste native JSON, edit independent accounts, preview and save the real mapping', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  let tested: any;
  await page.route('**/remote/cloud/admin/models/test-draft', async route => {
    tested = route.request().postDataJSON();
    await route.fulfill({ json: { ok: true, published: false } });
  });
  await page.goto('/admin');
  await page.getByRole('button', { name: '新建', exact: true }).click();
  await page.getByText('粘贴 OpenCode 原生 JSON / JSONC 填入表单', { exact: true }).click();
  const id = 'browser-pool-' + Date.now();
  const name = 'Coding pool ' + id;
  const native = { provider: { minimax: { npm: '@ai-sdk/openai-compatible',
    options: { apiKey: 'fake-account-a', baseURL: 'https://api.minimaxi.com/v1' },
    models: { 'MiniMax-M3': { name } } } } };
  await page.getByLabel('OpenCode JSON', { exact: true }).fill(JSON.stringify(JSON.stringify(native)));
  await page.getByRole('button', { name: '解析 JSON', exact: true }).click();
  await page.getByRole('button', { name: '填入当前表单（不保存）', exact: true }).click();
  await expect(page.getByLabel('上游模型 ID', { exact: true })).toHaveValue('MiniMax-M3');
  await page.getByLabel('稳定 ID', { exact: true }).fill(id);
  await page.getByRole('button', { name: '添加独立 API key（启用多账户）', exact: true }).click();
  await expect(page.getByLabel('账户 1 API key', { exact: true })).toHaveValue('fake-account-a');
  await page.getByLabel('账户 2 API key', { exact: true }).fill('fake-account-b');
  await page.getByLabel('账户 1 RPM', { exact: true }).fill('60');
  await page.getByLabel('账户 2 RPM', { exact: true }).fill('120');
  await page.getByRole('button', { name: '测试账户 2', exact: true }).click();
  await expect(page.getByText('连接测试通过', { exact: true })).toBeVisible();
  expect(tested.model.deployments).toHaveLength(1);
  expect(tested.model.deployments[0].api_key).toBe('fake-account-b');
  await expect(page.getByText('2 个启用部署', { exact: false }).last()).toBeVisible();
  await page.getByRole('heading', { name: '实际映射', exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByText('Internal Server Error', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: '../../artifacts/verification/model-routing-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.screenshot({ path: '../../artifacts/verification/model-routing-mobile.png', fullPage: true });
  await page.getByRole('button', { name: '保存到服务器', exact: true }).click();
  await expect(page.getByText('草稿已保存到服务器；发布后才生效', { exact: true })).toBeVisible();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  const card = page.getByText(name, { exact: true }).locator('..').locator('..');
  await card.getByRole('button', { name: '编辑', exact: true }).click();
  await expect(page.getByLabel('账户 1 API key', { exact: true })).toHaveValue('••••');
  await expect(page.getByLabel('账户 2 API key', { exact: true })).toHaveValue('••••');
  expect(errors).toEqual([]);
});
