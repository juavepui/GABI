import { expect, test } from '@playwright/test';
import type { RankingResponse } from '../../src/shared/api/generated/types.gen';

test('cobertura parcial y filtros vacíos conservan el estado del universo y la URL', async ({
  page,
  request,
}) => {
  const original: RankingResponse = await (
    await request.get('http://127.0.0.1:8001/api/v1/ranking')
  ).json();
  let posts = 0;
  page.on('request', (req) => {
    if (req.method() === 'POST') posts++;
  });
  await page.goto('/mercado?search=UNKNOWN');
  await expect(page.getByText('No hay empresas con estos filtros')).toBeVisible();
  const state = page.getByRole('region', { name: 'Estado de los datos' });
  await expect(state.getByText('Datos cacheados disponibles')).toBeVisible();
  await state.getByText(/Avisos de datos/).click();
  await expect(
    state.getByText('Cobertura parcial: faltan datos en parte del universo.'),
  ).toBeVisible();
  await expect(state).not.toContainText('incomplete_coverage');
  await page.reload();
  await expect(page).toHaveURL(/search=UNKNOWN/);
  await expect(state.getByText('Con datos SEC')).toBeVisible();
  await expect(state).toContainText(String(original.data.universe_count));
  expect(posts).toBe(0);
});

test('datos obsoletos, ausencia y errores de lectura tienen motivos y acciones distintos', async ({
  page,
  request,
}) => {
  const original: RankingResponse = await (
    await request.get('http://127.0.0.1:8001/api/v1/ranking')
  ).json();
  let scenario = 'stale';
  let posts = 0;
  page.on('request', (req) => {
    if (req.method() === 'POST') posts++;
  });
  await page.route('**/api/v1/ranking?*', (route) => {
    if (scenario === 'error')
      return route.fulfill({
        status: 503,
        json: {
          status: 'error',
          error: {
            code: 'data_read_error',
            message: 'No se pueden consultar los datos locales cacheados.',
          },
        },
      });
    return route.fulfill({
      json:
        scenario === 'empty'
          ? {
              ...original,
              items: [],
              total: 0,
              data: {
                ...original.data,
                status: 'empty',
                needs_attention: true,
                universe_count: 0,
                prices_available: 0,
                fundamentals_available: 0,
                sec_available: 0,
                scored_count: 0,
                warnings: [],
                latest_price_date: null,
              },
            }
          : {
              ...original,
              data: {
                ...original.data,
                status: 'stale',
                needs_attention: true,
                warnings: ['prices_stale', 'sec_stale'],
              },
            },
    });
  });
  await page.goto('/mercado?search=T000');
  const state = page.getByRole('region', { name: 'Estado de los datos' });
  await expect(state.getByText('Datos obsoletos', { exact: true })).toBeVisible();
  await expect(state.getByText('Hay precios fuera del plazo de frescura.')).toBeVisible();
  await expect(
    state.getByRole('link', { name: 'Actualizar datos desde Administración' }),
  ).toHaveAttribute('href', '/administracion');
  // Stale data keeps its full notice; the usual evidence notice folds into the chip (#187).
  await expect(page.getByText('Ventaja frente a SPY no demostrada')).toBeHidden();
  await page.getByText(/Evidencia: no demostrada/).click();
  await expect(page.getByText('Ventaja frente a SPY no demostrada')).toBeVisible();
  scenario = 'empty';
  await page.reload();
  await expect(page.getByText('Sin datos locales suficientes')).toBeVisible();
  await expect(page.getByText('La caché local no contiene empresas')).toBeVisible();
  scenario = 'error';
  await page.reload();
  await expect(page.getByRole('heading', { name: 'No se pueden cargar los datos' })).toBeVisible();
  await expect(
    page.getByText('Reintentar vuelve a consultar los datos locales; no inicia una descarga.'),
  ).toBeVisible();
  scenario = 'stale';
  await page.getByRole('button', { name: 'Reintentar', exact: true }).click();
  await expect(state.getByText('Datos obsoletos', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/search=T000/);
  expect(posts).toBe(0);
});

test('la ficha conserva fuentes y fechas por empresa junto al estado del universo', async ({
  page,
}) => {
  await page.goto('/mercado/empresas/T000');
  await expect(page.getByRole('region', { name: 'Estado de los datos' })).toContainText(
    'Fuentes: caché local de Yahoo y SEC',
  );
  await expect(page.getByText('Fundamentales · Yahoo', { exact: true })).toBeVisible();
  await expect(page.getByText('Información · SEC', { exact: true })).toBeVisible();
  await expect(page.getByText(/no constituyen un análisis histórico point-in-time/)).toBeVisible();
});
