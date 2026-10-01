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

test('resultado posterior del ranking es un job Research con corte observado', async ({ page }) => {
  await page.goto('/administracion');
  await page.getByRole('button', { name: 'Activar Research' }).click();
  await expect(page.getByText('Modo de trabajo · Research')).toBeVisible();
  try {
    await page.goto('/investigacion/historico');
    await page.getByRole('button', { name: 'Calcular ranking' }).click();
    const panel = page.getByRole('region', {
      name: 'Resultado posterior de las primeras candidatas',
    });
    await panel.getByRole('button', { name: 'Evaluar resultado posterior' }).click();
    await expect(panel.getByText(/6 meses: candidatas \+5,0 %/)).toBeVisible();
    await expect(panel.getByRole('row', { name: /^Value/ })).toContainText('+12,0 %');
  } finally {
    await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
      data: { mode: 'INVESTOR' },
    });
  }
});

test('Research Lab lista experimentos y su entorno solo en modo Research', async ({ page }) => {
  await page.goto('/investigacion/laboratorio');
  await expect(page.getByText('Research Lab requiere el modo Research local.')).toBeVisible();
  await page.goto('/administracion');
  await page.getByRole('button', { name: 'Activar Research' }).click();
  await expect(page.getByText('Modo de trabajo · Research')).toBeVisible();
  try {
    await page.goto('/investigacion/laboratorio');
    const table = page.getByRole('table', { name: 'Experimentos registrados' });
    await expect(table.getByRole('row', { name: /GABI-MF-v1\.0/ })).toContainText('-21.0 %');
    await page.getByLabel('Fase').selectOption('OUT_OF_SAMPLE');
    await expect(table.getByRole('row')).toHaveCount(2);
    await expect(table).toContainText('Fixture fuera de muestra');
    await page.getByLabel('Fase').selectOption('');
    await page.getByRole('button', { name: 'Ver entorno del experimento 1' }).click();
    const detail = page.getByRole('region', { name: 'Experimento 1' });
    await expect(detail.getByText('0123456789ab')).toBeVisible();
    await expect(detail.getByText('fixture-data')).toBeVisible();
    await expect(detail.getByRole('row', { name: /pandas/ })).toContainText('2.3.0');
    await expect(detail.getByText('3 observaciones, 2019-03-29 – 2019-09-30')).toBeVisible();
    const dsr = page.getByRole('region', { name: 'Probabilistic y Deflated Sharpe' });
    await dsr.getByLabel('Experimento a evaluar').selectOption('1');
    const dsrResult = dsr.getByRole('region', { name: 'Resultado PSR y DSR' });
    await expect(dsrResult).toContainText('Con N=2 intentos probados en la familia «mf-v1»');
    await expect(dsrResult).toContainText('asimetría y curtosis estimadas');
    await page.getByText('Riesgo de cola · serie guardada de un experimento').click();
    await page.getByLabel('Experimento con retornos').selectOption('1');
    await expect(
      page.getByRole('region', { name: 'Riesgo de cola del experimento' }),
    ).toContainText('Horizonte: un trimestre.');
  } finally {
    await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
      data: { mode: 'INVESTOR' },
    });
  }
});

test('Research Lab calcula PBO y bootstrap por bloques como jobs explícitos', async ({ page }) => {
  await page.goto('/administracion');
  await page.getByRole('button', { name: 'Activar Research' }).click();
  await expect(page.getByText('Modo de trabajo · Research')).toBeVisible();
  try {
    await page.goto('/investigacion/laboratorio');
    const pbo = page.getByRole('region', { name: 'PBO CSCV' });
    await pbo.getByLabel(/GABI-PBO-A/).check();
    await pbo.getByLabel(/GABI-PBO-B/).check();
    await pbo.getByRole('button', { name: 'Calcular PBO' }).click();
    const pboResult = pbo.getByRole('region', { name: 'Resultado PBO' });
    await expect(pboResult).toContainText('70 combinaciones IS/OOS evaluadas · 8 bloques');
    await expect(pboResult).toContainText(/PBO \d/);
    const boot = page.getByRole('region', { name: 'Incertidumbre por bloques' });
    await boot
      .getByLabel('Experimento para calcular incertidumbre')
      .selectOption({ label: '#4 · GABI-PBO-A' });
    await boot.getByLabel('Serie de comparación (misma frecuencia y fechas)').selectOption({
      label: '#5 · GABI-PBO-B',
    });
    await boot.getByRole('button', { name: 'Calcular distribuciones e intervalos' }).click();
    const bootResult = boot.getByRole('region', { name: 'Resultado del bootstrap' });
    await expect(bootResult).toContainText('40 observaciones · 4 por año');
    await expect(bootResult.getByRole('table', { name: 'Intervalos bootstrap' })).toContainText(
      'GABI frente a benchmark',
    );
    await bootResult
      .getByRole('combobox', { name: 'Distribución del remuestreo' })
      .selectOption('vs_benchmark/excess_mean');
    await expect(
      bootResult.getByRole('img', { name: /Exceso medio por observación/ }),
    ).toBeVisible();
    await bootResult.getByText('Parámetros y descarga reproducible').click();
    await expect(
      bootResult.getByRole('link', { name: 'Descargar todas las réplicas' }),
    ).toHaveAttribute('href', /distributions\.csv$/);
  } finally {
    await page.request.post('http://127.0.0.1:8001/api/v1/administration/mode', {
      data: { mode: 'INVESTOR' },
    });
  }
});
