import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('responsive navigation, filters, table and company on narrow screens', async ({
  page,
}, testInfo) => {
  await page.goto('/mercado?search=BRK');
  await expect(page.locator('tbody tr')).toHaveCount(2);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await expect(page.getByRole('button', { name: 'Aplicar filtros' })).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('market-mobile.png'), fullPage: true });
  await page.getByRole('link', { name: /BRK-B.*Company/ }).click();
  await expect(page.getByRole('heading', { name: 'Company BRK-B', exact: true })).toBeVisible();
  await expect(page.getByText(/Ver datos del gráfico/)).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('company-mobile.png'), fullPage: true });
  const layout = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    oversized: Array.from(document.querySelectorAll('body *'))
      .filter(
        (element) =>
          !element.closest('nav') && element.getBoundingClientRect().right > window.innerWidth + 1,
      )
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        className: typeof element.className === 'string' ? element.className.slice(0, 100) : '',
        right: Math.round(element.getBoundingClientRect().right),
      }))
      .sort((a, b) => b.right - a.right)
      .slice(0, 16),
  }));
  expect(layout.document, JSON.stringify(layout.oversized)).toBeLessThanOrEqual(layout.viewport);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole('link', { name: 'Volver al Screener' }).click();
  await expect(page).toHaveURL(/search=BRK/);
  await page.getByRole('link', { name: 'Administración', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Disponible en Streamlit' })).toBeVisible();
});
