import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const MODE = 'http://127.0.0.1:8001/api/v1/administration/mode';
const setMode = (page: Page, mode: 'INVESTOR' | 'RESEARCH') =>
  page.request.post(MODE, { data: { mode } });

const SCREENS: [string, string, RegExp | string][] = [
  ['hoy', '/', 'Tu GABI hoy'],
  ['ranking', '/descubrir', /Ranking/],
  ['ficha', '/empresas/T000', 'Company T000'],
  ['cartera', '/cartera', 'Mi cartera objetivo'],
  ['mapa', '/descubrir/mapa', 'Mapa del mercado'],
  ['macro', '/macro', 'Economía (macro)'],
  ['seguidas', '/descubrir/seguidas', 'Empresas seguidas'],
  ['investigacion', '/investigacion', /Investigación/],
];

test.afterEach(async ({ page }) => {
  await setMode(page, 'INVESTOR');
});

for (const theme of ['light', 'dark'] as const) {
  test(`contraste AA en las pantallas principales en tema ${theme === 'light' ? 'claro' : 'oscuro'} (#321)`, async ({
    page,
  }, testInfo) => {
    test.setTimeout(120_000);
    await setMode(page, 'RESEARCH');
    await page.addInitScript((value) => localStorage.setItem('gabi-theme', value), theme);
    for (const [name, path, heading] of SCREENS) {
      await page.goto(path);
      await expect(
        page.getByRole('heading', { name: heading, exact: typeof heading === 'string' }).first(),
      ).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('html')).toHaveClass(theme === 'dark' ? /dark/ : /^(?!.*dark)/);
      // Let lazy charts and queries settle before measuring.
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: testInfo.outputPath(`${name}-${theme}.png`), fullPage: true });
      const results = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();
      const failures = results.violations.flatMap((violation) =>
        violation.nodes.map((node) => `${path}: ${node.target.join(' ')} — ${node.failureSummary}`),
      );
      expect(failures, `${name} en ${theme}`).toEqual([]);
    }
  });
}
