import { expect, test } from '@playwright/test';

test('cartera y diario conservan el plan y las tesis locales', async ({ page }) => {
  await page.goto('/cartera');
  await expect(page.getByRole('heading', { name: 'Mi cartera objetivo' })).toBeVisible();
  await expect(page.getByText('Top-20 congelado')).toBeVisible();
  await page.getByLabel('Posiciones actuales (SÍMBOLO,euros; una por línea)').fill('T000,100');
  await page.getByRole('button', { name: 'Calcular plan' }).click();
  await expect(page.getByRole('heading', { name: 'Dónde aportar capital nuevo' })).toBeVisible();
  await page.getByRole('link', { name: /^Diario de inversión/ }).click();
  await page.getByText('Nueva tesis').click();
  await page.getByLabel('Símbolo').fill('T000');
  await page.getByLabel('Precio entrada (USD)').fill('100');
  await page.getByLabel('Tesis', { exact: true }).fill('Prueba local de tesis');
  await page.getByRole('button', { name: 'Guardar tesis' }).click();
  await expect(page.getByText('Prueba local de tesis')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Prueba local de tesis')).toBeVisible();
  await page.getByRole('button', { name: 'Marcar revisada' }).click();
  await expect(page.getByText('Revisada el')).toBeVisible();
  await page.getByLabel('Mostrar solo entradas abiertas (sin revisar)').check();
  await expect(page.getByText('Prueba local de tesis')).toHaveCount(0);
});

test('comparación y macro leen los contratos de Mercado', async ({ page }) => {
  await page.goto('/mercado/comparar');
  await page.getByRole('combobox', { name: 'Empresa 1' }).fill('t000');
  await page.getByRole('option', { name: /T000/ }).click();
  const second = page.getByRole('combobox', { name: 'Empresa 2' });
  await second.fill('001'); // Search anywhere in the symbol, not only by its first letter.
  await second.press('Enter');
  await expect(page.getByRole('heading', { name: 'Métricas comparables' })).toBeVisible();
  await expect(page.getByRole('row', { name: /Composite Score/ })).toBeVisible();
  await page.goto('/mercado/macro');
  await expect(page.getByRole('heading', { name: 'Panel macro' })).toBeVisible();
  await expect(page.getByText('Treasury 10 años')).toBeVisible();
  await expect(page.getByText('FRED', { exact: false }).first()).toBeVisible();
});

test('Signal Monitor conserva snapshots y compara con el ranking en vivo', async ({ page }) => {
  await page.goto('/mercado/senales');
  await expect(page.getByRole('heading', { name: 'Signal Monitor' })).toBeVisible();
  await page.getByRole('button', { name: 'Guardar foto' }).click();
  await expect(page.getByText(/Snapshot #\d+ guardado/)).toBeVisible();
  await page.reload();
  const tracking = page.getByRole('region', { name: 'Seguimiento del ranking guardado' });
  await expect(tracking).toContainText('Progreso desde');
  await expect(tracking.getByText(/6 meses: pendiente hasta/)).toBeAttached();
  await tracking.getByLabel('Cambiar nombre de este ranking').fill('Ranking e2e');
  await tracking.getByRole('button', { name: 'Guardar nombre' }).click();
  await expect(tracking).toContainText('Ranking e2e');
  await page.getByRole('button', { name: 'Comparar ahora' }).click();
  await expect(page.getByText('cambios detectados')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Próximos earnings' })).toBeVisible();
  await page.getByRole('button', { name: 'Comprobar filings' }).click();
  await expect(page.getByText(/pares con datos comparables/)).toBeVisible();
  await page.getByRole('button', { name: 'Guardar comparación y eventos' }).click();
  await expect(page.getByText('Comparación SEC guardada en la base local.')).toBeVisible();
  const filtered = page.waitForRequest(
    (request) =>
      request.url().includes('severity=MATERIAL') && request.url().includes('since_hours=24'),
  );
  await page.getByRole('combobox', { name: 'Severidad' }).selectOption('MATERIAL');
  await page.getByLabel('Últimas N horas').fill('24');
  await filtered;
});

test('cartera simulada conserva operaciones y calcula costes con caché local', async ({ page }) => {
  await page.goto('/cartera/simuladas');
  await expect(page.getByRole('heading', { name: 'Carteras simuladas' })).toBeVisible();
  await page.getByText('Crear cartera simulada').click();
  await page.getByLabel('Nombre').fill('Prueba de simulación');
  await page.getByRole('button', { name: 'Crear cartera' }).click();
  await expect(page.getByRole('heading', { name: /Prueba de simulación/ })).toBeVisible();
  await page.getByLabel('Símbolo').fill('T000');
  await page.getByLabel('Fecha').fill('2026-09-28');
  await page.getByLabel('Importe cotizado').fill('100');
  await page.getByRole('button', { name: 'Registrar operación' }).click();
  await expect(page.getByText('Operación registrada.')).toBeVisible();
  const prices = page.getByRole('region', { name: 'Precios públicos' });
  await prices.getByRole('button', { name: 'Actualizar precios de esta cartera y SPY' }).click();
  await expect(prices.getByText('Actualizados 2 símbolos; fallos: 0.')).toBeVisible({
    timeout: 15_000,
  });
  await prices.getByLabel('Ticker').fill('asml');
  await prices.getByRole('button', { name: 'Actualizar precios de este ticker' }).click();
  await expect(prices.getByText('Actualizados 4 símbolos; fallos: 0.')).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole('button', { name: 'Calcular resultado' }).click();
  await expect(page.getByRole('heading', { name: /Resultado simulado/ })).toBeVisible();
  await page.reload();
  await expect(page.getByText('2026-09-28 · BUY · T000')).toBeVisible();
  await page.getByRole('button', { name: 'Calcular comparación' }).click();
  await expect(page.getByRole('row', { name: /Prueba de simulación/ })).toBeVisible();
});

test('decisiones experimentales se calculan en job y persisten con su política', async ({
  page,
}) => {
  await page.goto('/cartera/decisiones');
  await expect(page.getByRole('heading', { name: 'Decisiones de cartera' })).toBeVisible();
  await page.getByRole('button', { name: 'Generar decisiones' }).click();
  await expect(page.getByText(/Método:/)).toBeVisible();
  const previewCsv = page.getByRole('link', { name: 'Descargar decisiones CSV' });
  const csv = await page.request.get((await previewCsv.getAttribute('href'))!);
  expect(csv.ok()).toBe(true);
  const header = (await csv.text()).replace(/^\uFEFF/, '').split('\n')[0];
  expect(header).toBe('symbol,action,current_pct,target_pct,change_pct,reason,score');
  await page.getByRole('button', { name: 'Guardar plan' }).click();
  await expect(page.getByText(/Plan #\d+ guardado/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Planes anteriores' })).toBeVisible();
  await expect(page.getByText('Progreso desde el plan')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Descargar decisiones CSV' })).toHaveAttribute(
    'href',
    /\/api\/v1\/portfolio\/decisions\/\d+\/decisions\.csv$/,
  );
});

test('aprender: tutorial completo con definiciones de métricas del backend', async ({ page }) => {
  await page.goto('/cartera/aprender');
  await expect(page.getByRole('heading', { name: 'Aprender a usar GABI' })).toBeVisible();
  await page.getByRole('tab', { name: 'Términos útiles' }).click();
  const valuation = page.getByRole('region', { name: 'Valoración (¿está cara o barata?)' });
  await valuation.getByText('PER', { exact: true }).click();
  await expect(valuation.getByText(/Precio\/Beneficio: veces que el precio/)).toBeVisible();
  const metrics = page.getByRole('region', { name: 'Métricas que usa GABI' });
  await metrics.getByText('Value', { exact: true }).click();
  await expect(metrics.getByText('(puntúa)')).toHaveCount(13); // The 13 metrics that score, across the 4 blocks.
  await page.getByRole('tab', { name: 'Psicología de la inversión' }).click();
  await expect(page.getByText('Tres hábitos prácticos')).toBeVisible();
  await page.getByRole('tab', { name: 'Cómo piensa GABI' }).click();
  await expect(page.getByRole('img', { name: /cae un 28 %/ })).toBeVisible();
  await expect(page.getByRole('table', { name: 'Motor V1 frente a V2' })).toContainText('0,111');
  await expect(page.getByText(/Streamlit/)).toHaveCount(0);
});
