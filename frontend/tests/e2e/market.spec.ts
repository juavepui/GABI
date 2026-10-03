import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { writeFile } from 'node:fs/promises';
import type { RankingResponse, CompanyResponse } from '../../src/shared/api/generated/types.gen';
import { metric } from '../../src/shared/lib/format';

test('real API: filters, full-universe sorting, pagination, company and reload preserve the URL', async ({
  page,
  request,
}, testInfo) => {
  const api = await request.get(
    'http://127.0.0.1:8001/api/v1/ranking?order_by=market_cap&direction=asc&limit=10',
  );
  const expected: RankingResponse = await api.json();
  expect(api.ok()).toBeTruthy();
  await page.goto('/mercado?order_by=market_cap&direction=asc&limit=10');
  await expect(page.getByRole('heading', { name: 'Ranking de empresas' })).toBeVisible();
  const rows = page.locator('tbody tr');
  await expect(rows).toHaveCount(expected.items.length);
  for (const [i, item] of expected.items.entries()) {
    await expect(rows.nth(i)).toContainText(item.symbol);
    await expect(rows.nth(i)).toContainText(metric(item.metrics.price));
    await expect(rows.nth(i)).toContainText(metric(item.metrics.composite_score));
  }
  await page.getByRole('button', { name: 'Página siguiente' }).click();
  await expect(page).toHaveURL(/offset=10/);
  const second: RankingResponse = await (
    await request.get(
      'http://127.0.0.1:8001/api/v1/ranking?order_by=market_cap&direction=asc&limit=10&offset=10',
    )
  ).json();
  await expect(rows).toHaveCount(second.items.length);
  await expect(rows.first()).toContainText(second.items[0].symbol);
  await page.getByRole('textbox', { name: 'Buscar empresa o símbolo' }).fill('BRK');
  await page.getByText('Todos los sectores', { exact: true }).click();
  await page.getByRole('checkbox', { name: 'Financials', exact: true }).check();
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page).toHaveURL(/search=BRK/);
  expect(new URL(page.url()).searchParams.has('offset')).toBeFalsy();
  await expect(rows).toHaveCount(2);
  await page.reload();
  await expect(page.getByRole('textbox', { name: 'Buscar empresa o símbolo' })).toHaveValue('BRK');
  await expect(rows).toHaveCount(2);
  const rankingUrl = page.url();
  await page.getByRole('link', { name: /BRK-A.*Company/ }).click();
  await expect(page.getByRole('heading', { name: 'Company BRK-A', exact: true })).toBeVisible();
  const company: CompanyResponse = await (
    await request.get('http://127.0.0.1:8001/api/v1/companies/BRK-A?bars=252')
  ).json();
  await expect(
    page.getByText(metric(company.company.metrics.price), { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Ventaja frente a SPY no demostrada')).toBeVisible();
  await expect(page.getByRole('img', { name: /Histórico de cierre ajustado/ })).toBeVisible();
  await expect(page.getByRole('main')).toBeFocused();
  await page.getByRole('button', { name: '63 sesiones', exact: true }).click();
  await expect(page).toHaveURL(/bars=63/);
  await expect(
    page.getByText('Ver datos del gráfico (63 sesiones)', { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: '63 sesiones', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(
    page.getByText('Ver datos del gráfico (63 sesiones)', { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('company-desktop.png'), fullPage: true });
  await page.getByRole('link', { name: 'Volver al Screener' }).click();
  await expect(page).toHaveURL(rankingUrl);
  await expect(rows).toHaveCount(2);
  await page.getByRole('button', { name: 'Restablecer' }).click();
  await expect(rows).toHaveCount(15);
  await page.screenshot({ path: testInfo.outputPath('market-desktop.png'), fullPage: true });
});

test('empty filters, missing values, stale data and empty cache have distinct states', async ({
  page,
  request,
}) => {
  await page.goto('/mercado?search=UNKNOWN');
  await expect(page.getByText('No hay empresas con estos filtros')).toBeVisible();
  await page.goto('/mercado?search=EMPTY&hide_no_data=false');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody tr > td').getByText('—')).toHaveCount(4);
  const payload: RankingResponse = await (
    await request.get('http://127.0.0.1:8001/api/v1/ranking')
  ).json();
  await page.route('**/api/v1/ranking?*', (route) =>
    route.fulfill({
      json: {
        ...payload,
        data: { ...payload.data, status: 'stale', warnings: ['Precios de prueba obsoletos'] },
      },
    }),
  );
  await page.goto('/mercado');
  await expect(page.getByText(/Datos obsoletos/)).toBeVisible();
  await expect(page.getByText('Ventaja frente a SPY no demostrada')).toBeVisible();
  await page.unroute('**/api/v1/ranking?*');
  await page.route('**/api/v1/ranking?*', (route) =>
    route.fulfill({
      json: { ...payload, items: [], total: 0, data: { ...payload.data, status: 'empty' } },
    }),
  );
  await page.reload();
  await expect(page.getByText('La caché local no contiene empresas')).toBeVisible();
});

test('loading, sanitized errors and retry; a newer request wins over a delayed one', async ({
  page,
}) => {
  let fail = true;
  await page.route('**/api/v1/ranking?*', async (route) => {
    if (fail)
      await route.fulfill({
        status: 503,
        json: {
          status: 'error',
          error: { code: 'DATA_UNAVAILABLE', message: 'Datos locales no disponibles' },
        },
      });
    else await route.continue();
  });
  await page.goto('/mercado');
  await expect(page.getByRole('alert')).toContainText('Datos locales no disponibles');
  fail = false;
  await page.getByRole('button', { name: 'Reintentar' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(15);
  await page.unroute('**/api/v1/ranking?*');
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/api/v1/ranking?*', async (route) => {
    if (new URL(route.request().url()).searchParams.get('search') === 'T000') {
      await held;
      await route.continue().catch(() => {});
    } else await route.continue();
  });
  await page.getByRole('textbox', { name: 'Buscar empresa o símbolo' }).fill('T000');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.getByRole('status')).toContainText('Consultando la caché local');
  await page.getByRole('textbox', { name: 'Buscar empresa o símbolo' }).fill('BRK');
  await page.getByRole('button', { name: 'Aplicar filtros' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  release();
  await expect(page.locator('tbody')).not.toContainText('T000');
});

test('keyboard, semantic accessibility and bounded warm navigation', async ({ page }, testInfo) => {
  const requests: string[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/')) requests.push(request.url());
  });
  const start = Date.now();
  await page.goto('/mercado');
  await expect(page.locator('tbody tr')).toHaveCount(15);
  const coldMs = Date.now() - start;
  const session = await page.context().newCDPSession(page);
  const coldHeap = await session.send('Runtime.getHeapUsage');
  const initialCount = requests.length;
  expect(requests.filter((url) => url.includes('/ranking?')).length).toBe(1);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Saltar al contenido' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.getByRole('link', { name: /T000.*Company/ }).click();
  await expect(page.getByRole('heading', { name: 'Company T000', exact: true })).toBeVisible();
  await expect(page.getByText(/Ver datos del gráfico/)).toBeVisible();
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  const warmStart = Date.now();
  await page.getByRole('link', { name: 'Volver al Screener' }).click();
  await expect(page.locator('tbody tr')).toHaveCount(15);
  const warmMs = Date.now() - warmStart;
  const warmHeap = await session.send('Runtime.getHeapUsage');
  expect(requests.filter((url) => url.includes('/ranking?')).length).toBe(1);
  const measurement = JSON.stringify(
    {
      fixture: '16 companies, 320 sessions, temporary SQLite',
      coldMs,
      warmMs,
      coldJsHeapBytes: coldHeap.usedSize,
      warmJsHeapBytes: warmHeap.usedSize,
      initialRequests: initialCount,
      totalRequests: requests.length,
      rankingRequests: 1,
      companyWindow: 252,
    },
    null,
    2,
  );
  const measurementPath = testInfo.outputPath('bounded-navigation.json');
  await writeFile(measurementPath, measurement);
  await testInfo.attach('bounded-navigation.json', {
    path: measurementPath,
    contentType: 'application/json',
  });
});

test('evidencia del ranking, estabilidad y evidencia de una empresa se calculan al abrirlas', async ({
  page,
  request,
}) => {
  const top = await (await request.get('http://127.0.0.1:8001/api/v1/evidence')).json();
  await page.goto('/mercado');
  await expect(page.getByRole('heading', { name: 'Ranking de empresas' })).toBeVisible();
  const coverage = page.getByRole('region', { name: 'Cobertura de datos del ranking' });
  await coverage.getByLabel('Cobertura completa mínima (%)').fill('100');
  await expect(coverage.getByRole('status')).toContainText('Cobertura de datos degradada');
  await expect(coverage.getByRole('status')).toContainText('umbral configurado: 100%');
  await page.getByText('Evidencia del ranking · confianza de las candidatas del Top-20').click();
  const table = page.getByRole('table', { name: 'Evidencia del ranking' });
  await expect(table.getByRole('row')).toHaveCount(top.rows.length + 1);
  const first = top.rows[0].symbol;
  await table.getByRole('button', { name: first }).click();
  const detail = page.getByRole('region', { name: `Evidencia de ${first}` });
  await expect(detail).toContainText('Confianza de evidencia');
  await expect(detail.getByRole('table', { name: 'Factores del score' })).toBeVisible();
  await page.getByText('Estabilidad del ranking · cambios de 1–2 puntos en los pesos').click();
  await expect(
    page.getByRole('region', { name: 'Estabilidad del ranking' }).getByText(/perturbaciones/),
  ).toBeVisible();
  await page.goto('/mercado/empresas/' + first);
  await page.getByText('Evidencia de la candidatura').click();
  await expect(
    page.getByRole('link', { name: 'Descargar evidencia de la candidata' }),
  ).toBeVisible();
});

test('la ficha muestra catalizadores, métricas informativas, filings y sincroniza bajo demanda', async ({
  page,
}) => {
  await page.goto('/mercado/empresas/T001');
  await expect(page.getByText('Otras métricas (informativas, no puntuadas)')).toBeVisible();
  await expect(page.getByRole('region', { name: 'Próximos catalizadores' })).toBeVisible();
  await page.getByText('Qué cambió respecto al filing anterior').click();
  const changes = page.locator('details', { hasText: 'Qué cambió respecto al filing anterior' });
  await expect(changes.getByText(/^10-K/).first()).toBeVisible();
  await page.getByText('Historial de sorpresas de resultados').click();
  await page.getByRole('button', { name: 'Sincronizar historial de resultados' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Sincronizado.' })).toBeVisible();
  await page.getByText('Estimaciones de consenso').click();
  await expect(page.getByText('Sin estimaciones sincronizadas todavía.')).toBeVisible();
  await page.getByText('Actividad de insiders (SEC Form 4, informativo)').click();
  await expect(page.getByText(/Sin operaciones de insiders en los últimos 6 meses/)).toBeVisible();
  await page.getByRole('button', { name: 'Actualizar insiders de esta empresa' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Sincronizado.' }).last()).toBeVisible();
  await page.getByText('Prompt para analizar con IA').click();
  await expect(page.getByLabel('Prompt para analizar con IA')).toHaveValue(
    /No recalcules estos números/,
  );
});

test('la portada muestra el aviso legal y el rebalanceo ciego próximo', async ({ page }) => {
  await page.goto('/');
  const notices = page.getByRole('region', { name: 'Avisos' });
  await expect(notices.getByText('No es asesoramiento financiero.')).toBeVisible();
  await expect(
    notices.getByText(
      /Rebalanceo de la prueba ciega #1 \(Fixture ciega\) en 2 días, el 2026-10-01/,
    ),
  ).toBeVisible();
  await expect(notices.getByText(/#44/)).toHaveCount(0);
  await notices.getByRole('link', { name: 'Investigación → Validaciones ciegas' }).click();
  await expect(page.getByRole('region', { name: 'Avisos' })).toHaveCount(0);
});

test('un sistema en modo oscuro no oscurece los avisos del tema claro', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  const notice = page.getByRole('region', { name: 'Avisos' }).getByText(/No es asesoramiento/);
  await expect(notice).toBeVisible();
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(247, 248, 245)');
  await expect(page.locator('html')).toHaveCSS('color-scheme', 'light');
});

test('la portada resume datos, cartera objetivo y primeros pasos sin descargar nada', async ({
  page,
}) => {
  const requests: string[] = [];
  page.on('request', (request) => requests.push(request.method() + ' ' + request.url()));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Tu GABI hoy' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Inicio', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  const data = page.getByRole('region', { name: 'Estado de los datos' });
  await expect(data.getByText('Empresas puntuadas')).toBeVisible({ timeout: 30_000 });
  const target = page.getByRole('region', { name: 'Cartera objetivo de hoy' });
  await expect(target.getByRole('listitem').first()).toBeVisible();
  // The home page itself only reads: no POST (no job, no download).
  expect(requests.filter((line) => line.startsWith('POST'))).toEqual([]);
  await target.getByRole('link', { name: 'Ver la cartera y repartir capital' }).click();
  await expect(page.getByRole('heading', { name: 'Mi cartera objetivo' })).toBeVisible();
});

test('la tabla de Mercado colorea por percentil, fija la cabecera y alinea números', async ({
  page,
}) => {
  await page.goto('/mercado?limit=100');
  const scroll = page.getByRole('region', { name: 'Tabla desplazable' });
  const firstRow = scroll.locator('tbody tr').first();
  await expect(firstRow).toBeVisible({ timeout: 30_000 });
  // The score cell is coloured (red to green) and right-aligned; prices are not coloured.
  const scoreCell = firstRow.locator('td').nth(2);
  await expect(scoreCell).toHaveCSS('text-align', 'right');
  expect(await scoreCell.evaluate((cell) => getComputedStyle(cell).backgroundColor)).toMatch(
    /^rgb\(/,
  );
  await expect(page.getByText(/percentil dentro del sector/)).toBeVisible();
  // Scrolling the table keeps its header row in view.
  await scroll.evaluate((element) => element.scrollTo(0, element.scrollHeight));
  const header = scroll.locator('thead th').first();
  const [headerBox, regionBox] = await Promise.all([header.boundingBox(), scroll.boundingBox()]);
  expect(Math.abs((headerBox?.y ?? 0) - (regionBox?.y ?? 0))).toBeLessThan(4);
});
