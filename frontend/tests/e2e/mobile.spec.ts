import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('home summarizes local data and portfolio without horizontal scrolling on mobile', async ({
  page,
}) => {
  const writes: string[] = [];
  page.on('request', (request) => {
    if (request.method() !== 'GET') writes.push(request.method() + ' ' + request.url());
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Tu GABI hoy' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Avisos' })).toContainText(
    'No es asesoramiento financiero.',
  );
  const data = page.getByRole('region', { name: 'Estado de los datos' });
  await expect(data.getByText('Empresas puntuadas')).toBeVisible({ timeout: 30_000 });
  const target = page.getByRole('region', { name: 'Cartera objetivo de hoy' });
  await expect(target.getByRole('listitem').first()).toBeVisible();
  expect(writes).toEqual([]);
  const layout = await page.evaluate(() => ({
    viewport: innerWidth,
    width: document.documentElement.scrollWidth,
    oversized: Array.from(document.querySelectorAll('body *'))
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .map((element) => ({
        tag: element.tagName,
        className: typeof element.className === 'string' ? element.className : '',
        label: element.getAttribute('aria-label'),
        left: Math.round(element.getBoundingClientRect().left),
        right: Math.round(element.getBoundingClientRect().right),
      }))
      .slice(0, 12),
  }));
  expect(layout.width, JSON.stringify(layout.oversized)).toBeLessThanOrEqual(layout.viewport);
  await page.setViewportSize({ width: 320, height: 640 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await target.getByRole('link', { name: 'Ver la cartera y repartir capital' }).click();
  await expect(page.getByRole('heading', { name: 'Mi cartera objetivo' })).toBeVisible();
});

test('responsive navigation, filters, table and company on narrow screens', async ({
  page,
}, testInfo) => {
  await page.goto('/mercado?search=BRK');
  await expect(page.locator('tbody tr')).toHaveCount(2);
  const ranking = page.getByRole('region', { name: 'Ranking de empresas' });
  await expect(ranking.getByText('Más métricas de BRK-B')).toBeVisible();
  await ranking.getByText('Más métricas de BRK-B').click();
  await expect(
    ranking.locator('details[open] dt').filter({ hasText: 'Capitalización' }),
  ).toBeVisible();
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
          !element.closest('nav') &&
          (element.getBoundingClientRect().right > window.innerWidth + 1 ||
            (element.clientWidth > 0 &&
              element.scrollWidth > element.clientWidth + 1 &&
              getComputedStyle(element).overflowX === 'visible')),
      )
      .map((element) => ({
        tag: element.tagName.toLowerCase(),
        className: typeof element.className === 'string' ? element.className.slice(0, 100) : '',
        right: Math.round(element.getBoundingClientRect().right),
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      }))
      .sort((a, b) => b.right - a.right)
      .slice(0, 16),
  }));
  expect(layout.document, JSON.stringify(layout.oversized)).toBeLessThanOrEqual(layout.viewport);
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole('main').getByRole('link', { name: 'Ranking', exact: true }).click();
  await expect(page).toHaveURL(/search=BRK/);
  await page.getByRole('link', { name: 'Administración', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Administración' })).toBeVisible();
});

test('comparison shows one company per mobile card with its full metric detail', async ({
  page,
}) => {
  await page.goto('/mercado/comparar?symbols=T000&symbols=T001');
  const cards = page.locator('[aria-label="Comparación por empresa"]');
  await expect(cards.getByRole('article')).toHaveCount(2);
  await expect(cards.getByText('Composite Score')).toHaveCount(2);
  await cards.getByText('Todas las métricas de T000').click();
  await expect(
    cards
      .getByRole('article')
      .first()
      .locator('details[open] dt')
      .filter({ hasText: 'Precio / valor contable' }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
});

test('Research Lab shows essential experiment data and an expandable detail on mobile', async ({
  page,
}) => {
  await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
    data: { mode: 'RESEARCH' },
  });
  try {
    await page.goto('/investigacion/laboratorio');
    const cards = page.locator('div[aria-label="Experimentos registrados"]');
    const first = cards.getByRole('article').first();
    await expect(first).toContainText('Sharpe');
    await first.getByText('Más datos del experimento').click();
    await expect(first.getByText('Máx. drawdown')).toBeVisible();
    const select = first.getByRole('button', { name: /Experimento #/ });
    const id = (await select.textContent())!.match(/\d+/)![0];
    await select.click();
    await expect(page.getByRole('region', { name: `Experimento ${id}` })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    ).toBeTruthy();
  } finally {
    await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
      data: { mode: 'INVESTOR' },
    });
  }
});

test('portfolio target keeps weights visible and expands secondary metrics on mobile', async ({
  page,
}) => {
  await page.goto('/cartera');
  const target = page.getByRole('region', { name: 'Cartera objetivo' });
  const detail = target.getByText(/^Más datos de/).first();
  await expect(detail).toBeVisible();
  await detail.click();
  await expect(target.locator('details[open] dt').filter({ hasText: 'Precio USD' })).toBeVisible();
  await expect(target.getByRole('columnheader', { name: 'Peso' })).toBeVisible();
  await expect(target.getByRole('columnheader', { name: 'Importe' })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
});

test('en móvil la pestaña activa queda a la vista y ninguna sección desborda', async ({ page }) => {
  const inView = async (name: string, menu: string) => {
    const link = page
      .getByRole('navigation', { name: menu })
      .getByRole('link', { name, exact: true });
    const box = (await link.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
  };
  await page.goto('/investigacion/laboratorio');
  await expect(page.getByRole('heading', { name: 'Research Lab' })).toBeVisible();
  await inView('Investigación', 'Navegación principal');
  await inView('Research Lab', 'Apartados de la sección');
  const top = await page.locator('main').evaluate((main) => main.getBoundingClientRect().top);
  expect(top).toBeLessThanOrEqual(200);
  for (const path of ['/', '/mercado', '/cartera', '/investigacion/historico', '/administracion']) {
    await page.goto(path);
    await expect(page.locator('main h1')).toBeVisible();
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, path).toBeLessThanOrEqual(390);
  }
});
