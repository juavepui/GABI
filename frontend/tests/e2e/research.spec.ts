import { expect, test } from '@playwright/test';

test('Investigación distingue ensayos fallidos de reservas pendientes', async ({ page }) => {
  await page.goto('/investigacion');
  await expect(page.getByRole('heading', { name: 'Investigación' })).toBeVisible();
  await expect(page.getByText('trial/failed')).toBeVisible();
  await expect(page.getByText('negative_excess')).toBeVisible();
  await expect(page.getByText('Prospectiva pendiente')).toBeVisible();
  await page.getByLabel('Familia').selectOption('forward_family');
  await expect(page.getByText('trial/pending')).toBeVisible();
  await expect(page.getByText('trial/failed')).toHaveCount(0);
});

test('ranking histórico se calcula en un job y muestra identidad y cobertura', async ({ page }) => {
  await page.goto('/investigacion');
  await page.getByRole('link', { name: 'Abrir ranking histórico' }).click();
  await expect(page.getByRole('heading', { name: 'Ranking histórico' })).toBeVisible();
  await page.getByRole('button', { name: 'Calcular ranking' }).click();
  await expect(page.getByRole('heading', { name: 'Ranking a 2019-01-02' })).toBeVisible();
  const table = page.getByRole('table', { name: 'Métricas reconstruidas' });
  await page.getByLabel('Ocultar empresas sin ningún dato reconstruido').uncheck();
  await expect(table.getByRole('row', { name: /T000/ })).toContainText('72,50');
  await expect(table.getByRole('row', { name: /T001/ })).toContainText('Fixture B');
  await table.getByRole('button', { name: 'Composite' }).click();
  await expect(table.getByRole('row').nth(1)).toContainText('T000');
  const coverage = page.getByRole('region', { name: 'Cobertura de la reconstrucción' });
  await expect(
    coverage.getByText(/1\/2 empresas sin identidad histórica acreditada/),
  ).toBeVisible();
  await expect(coverage.getByText('Cobertura de datos degradada', { exact: false })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Descargar resultado completo' })).toBeVisible();
});

test('validación ciega muestra integridad sin desvelar posiciones', async ({ page }) => {
  await page.goto('/investigacion');
  await page.getByRole('link', { name: 'Ver validaciones ciegas' }).click();
  await expect(page.getByRole('heading', { name: 'Validaciones ciegas' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '#1 · Fixture ciega' })).toBeVisible();
  await expect(page.getByText('Íntegra')).toBeVisible();
  await expect(page.getByText('SEALED_TICKER')).toHaveCount(0);
});

test('Factor Lab muestra el mapa publicado y la cobertura SIC sin recalcularlo', async ({
  page,
}) => {
  await page.goto('/investigacion/factores');
  const map = page.getByRole('region', { name: 'Mapa de evidencia por factor' });
  await expect(map.getByText('13 señales y 57 trimestres publicados.')).toBeVisible();
  await expect(map.getByText('ninguna señal supera la corrección Holm al 5 %.')).toBeVisible();
  await expect(map.getByRole('row', { name: /PER/ })).toContainText('0,266');
  await map.getByLabel('Señal · estabilidad por industria').selectOption('roic');
  await expect(map.getByRole('row', { name: /Manufactura/ })).toBeVisible();
  await expect(map.getByRole('link', { name: 'Descargar Cobertura y exclusiones' })).toBeVisible();
});

test('Factor Lab ejecuta un job y presenta el resultado exploratorio', async ({ page }) => {
  await page.goto('/administracion');
  await page.getByRole('button', { name: 'Activar Research' }).click();
  await expect(page.getByText('Modo de trabajo · Research')).toBeVisible();
  try {
    await page.goto('/investigacion');
    await page.getByRole('link', { name: 'Abrir Factor Lab' }).click();
    await expect(page.getByRole('heading', { name: 'Factor Lab' })).toBeVisible();
    await page.getByRole('button', { name: 'Ejecutar Factor Lab' }).click();
    await expect(page.getByRole('heading', { name: 'Resumen de factores' })).toBeVisible();
    await expect(page.getByRole('row', { name: /value_score 3 meses/ })).toContainText('0,12');
    await expect(page.getByRole('row', { name: /^Q1/ })).toContainText('2 %');
    await expect(page.getByRole('row', { name: /^Q5/ })).toContainText('5 %');
    await page.getByText('1 periodo(s) saltado(s)').click();
    await expect(page.getByText('2019-07-02: cobertura insuficiente')).toBeVisible();
    await expect(page.getByRole('link', { name: /Descargar series/ })).toBeVisible();
  } finally {
    await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
      data: { mode: 'INVESTOR' },
    });
  }
});

test('backtest V1 se ejecuta como job Research y conserva el resultado completo', async ({
  page,
}) => {
  await page.goto('/administracion');
  await page.getByRole('button', { name: 'Activar Research' }).click();
  await expect(page.getByText('Modo de trabajo · Research')).toBeVisible();
  try {
    await page.goto('/investigacion/historico');
    await expect(
      page.getByRole('heading', { name: 'Backtest multifactor por rebalanceos' }),
    ).toBeVisible();
    await page.getByRole('button', { name: 'Ejecutar backtest' }).click();
    const result = page.getByRole('region', { name: 'Resultado del backtest' });
    await expect(result.getByRole('heading', { name: /Resultado V1/ })).toBeVisible();
    await expect(result.getByRole('row', { name: /^Estrategia/ })).toContainText('12 %');
    await expect(result.getByRole('row', { name: /^SPY/ })).toContainText('0,45');
    await result.getByText('1 periodo(s) saltado(s)').click();
    await expect(result.getByText('2019-07-02: cobertura insuficiente')).toBeVisible();
    await expect(result.getByRole('link', { name: /Descargar backtest completo/ })).toBeVisible();
    await expect(result.getByText('Ningún rebalanceo por debajo del umbral.')).toBeVisible();
    await result.getByText(/^Riesgo de cola/).click();
    await expect(
      result.getByText('Horizonte: 3 meses (rebalanceo V1).', { exact: false }),
    ).toBeVisible();
    await result.getByText(/^Drag fiscal español/).click();
    await expect(result.getByText('SPY comprado y mantenido')).toBeVisible();
    await result.getByText(/^Contraste con factores académicos/).click();
    await result.getByRole('button', { name: 'Calcular contraste' }).click();
    const contrast = result.getByRole('region', { name: 'Contraste Fama-French' });
    await expect(contrast.getByText('t-stat del alfa (HAC)')).toBeVisible();
    await expect(contrast.getByRole('row', { name: /^Mkt-RF/ })).toContainText('1,02');
    await expect(contrast.getByText(/fixture sin trimestres suficientes/).first()).toBeVisible();
    await result.getByText('Registrar este experimento en Research Lab').click();
    await result.getByLabel('Familia (agrupa intentos comparables)').fill('mf-v1');
    await result.getByRole('button', { name: 'Registrar en Research Lab' }).click();
    await expect(result.getByText('Experimento #7 registrado en Research Lab.')).toBeVisible();
  } finally {
    await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
      data: { mode: 'INVESTOR' },
    });
  }
});

test('preparar datos de una fecha es un job explícito que lista los fallos', async ({ page }) => {
  await page.goto('/investigacion/historico');
  const section = page.getByRole('region', { name: 'Preparar datos de la fecha' });
  await section.getByLabel(/Empresas a preparar/).selectOption('50');
  await section.getByRole('button', { name: 'Preparar datos que falten para esta fecha' }).click();
  const result = section.getByRole('region', { name: 'Resultado de la preparación' });
  await expect(result.getByText('Preparación terminada · 50 símbolos')).toBeVisible();
  await result.getByText('Ver los 1 símbolos con algún fallo').click();
  await expect(result.getByText('T009 · precio · sin histórico en la fuente')).toBeVisible();
});
