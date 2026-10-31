import { expect, test } from '@playwright/test';

test('cartera y diario conservan el plan y las tesis locales', async ({ page }) => {
  await page.goto('/cartera');
  await expect(page.getByRole('heading', { name: 'Mi cartera objetivo' })).toBeVisible();
  await expect(page).toHaveTitle('Cartera objetivo · GABI');
  await expect(page.getByText('Top-20 congelado')).toBeVisible();
  await page
    .getByLabel('¿Y si…? Posiciones hipotéticas (SÍMBOLO,euros; una por línea)')
    .fill('T000,100');
  await page.getByRole('button', { name: 'Calcular plan' }).click();
  await expect(page.getByRole('heading', { name: 'Dónde aportar capital nuevo' })).toBeVisible();
  // The test universe is almost all Information Technology: the descriptive warning must show.
  const breakdown = page.getByRole('region', { name: 'Reparto por sector' });
  await expect(breakdown.getByRole('status')).toContainText('Sector Information Technology');
  await expect(breakdown.getByRole('columnheader', { name: 'S&P 500' })).toBeVisible();
  await expect(breakdown.getByRole('row', { name: /Information Technology/ })).toBeVisible();
  await page
    .getByRole('main')
    .getByRole('link', { name: /^Diario de inversión/ })
    .click();
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
  await page.goto('/descubrir/comparar');
  await page.getByRole('combobox', { name: 'Empresa 1' }).fill('t000');
  await page.getByRole('option', { name: /T000/ }).click();
  const second = page.getByRole('combobox', { name: 'Empresa 2' });
  await second.fill('001'); // Search anywhere in the symbol, not only by its first letter.
  await second.press('Enter');
  await expect(page.getByRole('heading', { name: 'Métricas comparables' })).toBeVisible();
  // The tab follows the choice, so several comparisons open at once can be told apart.
  await expect(page).toHaveTitle('Comparar T000, T001 · GABI');
  const composite = page.getByRole('row', { name: /Composite Score/ });
  await expect(composite).toBeVisible();
  // The better company on the score is green and marked as the best of the compared ones.
  const best = composite.locator('td[title="El mejor de los comparados"]');
  await expect(best).toHaveCount(1);
  await expect(best).toHaveCSS('background-color', 'rgb(199, 245, 199)');
  await page.goto('/macro');
  await expect(page.getByRole('heading', { name: 'Panel macro' })).toBeVisible();
  await expect(page.getByText('Treasury 10 años')).toBeVisible();
  // One line stays visible; the full explanation is folded under «Cómo leer esta página».
  await expect(page.getByText('no interviene en el score')).toBeVisible();
  const guide = page.getByText(/Estas series FRED no intervienen/);
  await expect(guide).toBeHidden();
  await page.getByText('Cómo leer esta página').click();
  await expect(guide).toBeVisible();
});

test('la cartera objetivo se guarda para seguirla y sus eventos están en Eventos (#193)', async ({
  page,
}) => {
  await page.goto('/cartera');
  await page.getByRole('button', { name: 'Guardar esta cartera para seguirla' }).click();
  await page.getByRole('status').getByRole('link', { name: 'Seguimiento' }).click();
  await expect(page).toHaveURL(/\/cartera\/seguimiento$/);
  await expect(
    page.getByRole('heading', { name: 'Seguimiento de cestas', level: 1 }),
  ).toBeVisible();
  await expect(page.getByLabel('Cesta guardada')).toContainText('Cartera objetivo · Top-20');
  const tracking = page.getByRole('region', { name: 'Seguimiento del ranking guardado' });
  await expect(tracking).toContainText('Progreso desde');
  await expect(tracking.getByText(/6 meses: pendiente hasta/)).toBeAttached();
  await tracking.getByLabel('Cambiar nombre de este ranking').fill('Ranking e2e');
  await tracking.getByRole('button', { name: 'Guardar nombre' }).click();
  await expect(tracking).toContainText('Ranking e2e');
  await page.getByRole('main').getByRole('link', { name: 'Eventos' }).click();
  await expect(page.getByRole('heading', { name: 'Eventos', level: 1 })).toBeVisible();
  await page.getByRole('button', { name: 'Comparar ahora' }).click();
  await expect(page.getByText('cambios detectados')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Próximos earnings' })).toBeVisible();
  await page.getByRole('button', { name: 'Comprobar filings' }).click();
  // The basket is today's whole target (20 companies): reading the SEC result takes longer.
  await expect(page.getByText(/pares con datos comparables/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: 'Guardar comparación y eventos' }).click();
  await expect(page.getByText('Comparación SEC guardada en la base local.')).toBeVisible();
  const filtered = page.waitForRequest(
    (request) =>
      request.url().includes('severity=MATERIAL') && request.url().includes('since_hours=24'),
  );
  await page.getByRole('combobox', { name: 'Severidad' }).selectOption({ label: 'Material' });
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
  await expect(
    prices.getByRole('button', { name: 'Actualizar precios de este ticker' }),
  ).toBeDisabled();
  await expect(prices.getByText('Escribe un ticker para descargar sus precios.')).toBeVisible();
  await prices.getByRole('button', { name: 'Actualizar precios de esta cartera y SPY' }).click();
  await expect(prices.getByText('Actualizados 2 símbolos; fallos: 0.')).toBeVisible({
    timeout: 15_000,
  });
  await prices.getByLabel('Ticker').fill('asml');
  await prices.getByRole('button', { name: 'Actualizar precios de este ticker' }).click();
  await expect(prices.getByText('Actualizados 4 símbolos; fallos: 0.')).toBeVisible({
    timeout: 15_000,
  });
  // The result against SPY shows without asking (#192).
  await expect(page.getByRole('heading', { name: /Resultado simulado/ })).toBeVisible();
  // A ticker without prices offers its download in the same step, then registers the trade.
  await page.getByLabel('Símbolo').fill('NUEVA');
  await page.getByLabel('Fecha').fill('2026-09-28');
  await page.getByLabel('Importe cotizado').fill('50');
  await page.getByRole('button', { name: 'Registrar operación' }).click();
  await expect(page.getByRole('alert')).toContainText('No hay precios de NUEVA');
  await page.getByRole('button', { name: 'Descargar precios de NUEVA y registrar' }).click();
  await expect(page.getByText('28 sept 2026 · BUY · NUEVA')).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await expect(page.getByText('28 sept 2026 · BUY · T000')).toBeVisible();
  await page.getByRole('button', { name: 'Calcular comparación' }).click();
  await expect(page.getByRole('row', { name: /Prueba de simulación/ })).toBeVisible();
});

test('decisiones experimentales se calculan en job y persisten con su política', async ({
  page,
}) => {
  // One plan page for both plans (#191): the experimental one is chosen on it.
  await page.goto('/cartera');
  await page.getByRole('radio', { name: 'Plan experimental con límites' }).click();
  await expect(page).toHaveURL(/\/cartera\?plan=experimental$/);
  await expect(page.getByRole('heading', { name: 'Nuevo plan' })).toBeVisible();
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
  await expect(page.getByText(/^Guardado hoy\./)).toBeVisible();
  await expect(page.getByRole('link', { name: 'Descargar decisiones CSV' })).toHaveAttribute(
    'href',
    /\/api\/v1\/portfolio\/decisions\/\d+\/decisions\.csv$/,
  );
});

test('aprender: tutorial completo con definiciones de métricas del backend', async ({ page }) => {
  await page.goto('/ayuda');
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

test('el icono ⓘ explica un término y lleva al glosario de la Ayuda', async ({ page }) => {
  await page.goto('/descubrir');
  const hint = page.getByRole('button', { name: 'Qué es percentil dentro del sector' });
  await hint.scrollIntoViewIfNeeded();
  await hint.click();
  const tip = page.locator('[data-term-tip]');
  await expect(tip).toContainText('Percentil sectorial');
  await expect(tip).toContainText('frente a las de su mismo sector');
  await page.keyboard.press('Escape');
  await expect(tip).toHaveCount(0);
  await hint.click();
  await tip.getByRole('link', { name: 'Más en la Ayuda' }).click();
  await expect(page).toHaveURL(/\/ayuda\?tab=glosario#termino-percentile$/);
  await expect(page.getByRole('tab', { name: 'Glosario' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  await expect(page.locator('#termino-percentile')).toContainText('Percentil sectorial');
  await expect(page.locator('#termino-psr')).toContainText('Probabilistic Sharpe Ratio');
});

test('Mi cartera guarda, edita, importa y borra compras sin descargar precios', async ({
  page,
}) => {
  await page.goto('/cartera/mi-cartera');
  await expect(page.getByRole('heading', { name: 'Mi cartera', level: 1 })).toBeVisible();
  const form = page.getByRole('region', { name: 'Registrar una compra' });
  await form.getByLabel('Símbolo').fill('T000');
  await form.getByLabel('Acciones').fill('10');
  await form.getByLabel('Precio por acción').fill('100');
  await form.getByLabel('Fecha de compra').fill('2026-06-01');
  await form.getByLabel('Euros por unidad (opcional)').fill('0.9');
  await form.getByRole('button', { name: 'Guardar compra' }).click();
  const lots = page.getByRole('region', { name: 'Compras registradas' });
  await expect(lots).toContainText('T000');
  await page.reload(); // The lot survives a reload: it lives in the local database.
  await expect(lots).toContainText('10 acciones');
  // The test cache has no EUR rate: the position is shown in dollars and flagged, never filled in.
  const prices = page.getByRole('region', { name: 'Precios de mi cartera' });
  await expect(prices.getByRole('status')).toContainText('T000');
  await expect(
    prices.getByRole('button', { name: 'Actualizar precios de mi cartera' }),
  ).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Posiciones' }).getByText('Sin tipo de cambio en caché'),
  ).toBeVisible();
  await lots.getByRole('button', { name: 'Editar compra de T000' }).click();
  await lots.getByLabel('Acciones').fill('12');
  await lots.getByRole('button', { name: 'Guardar cambios' }).click();
  await expect(lots).toContainText('12 acciones');

  await page.getByText('Importar CSV de un bróker').click();
  await page
    .getByLabel('Contenido del CSV')
    .fill('symbol,shares,price,date\nT001,1,50,2026-07-01\nT002,-1,50,2026-07-01');
  await page.getByRole('button', { name: 'Importar compras' }).click();
  await expect(page.getByText(/línea 3/)).toBeVisible(); // One wrong row rejects the whole file.
  await page.getByLabel('Contenido del CSV').fill('symbol,shares,price,date\nT001,1,50,2026-07-01');
  await page.getByRole('button', { name: 'Importar compras' }).click();
  await expect(page.getByText('Importadas 1 compras.')).toBeVisible();
  await expect(lots).toContainText('T001');

  await page.goto('/cartera');
  await expect(page.getByText('Calculado sobre Mi cartera')).toBeVisible();
  // The form still holds the values the page loaded with: the click recalculates anyway.
  const recalculated = page.waitForRequest('**/api/v1/portfolio/plan');
  await page.getByRole('button', { name: 'Calcular plan' }).click();
  await recalculated;
  await expect(page.getByText('Calculado sobre Mi cartera')).toBeVisible();

  await page.goto('/cartera/mi-cartera');
  for (const symbol of ['T000', 'T001'])
    await lots.getByRole('button', { name: 'Borrar compra de ' + symbol }).click();
  await expect(page.getByRole('region', { name: 'Compras registradas' })).toHaveCount(0);
});

test('formularios con valores del backend y «Opciones avanzadas» recordadas (#190)', async ({
  page,
  request,
}) => {
  const defaults = await (await request.get('http://127.0.0.1:8001/api/v1/forms/defaults')).json();
  await page.goto('/cartera/simuladas');
  await page.getByText('Crear cartera simulada').click();
  await expect(page.getByLabel('Capital inicial')).toHaveValue(
    String(defaults.simulation.initial_cash),
  );
  // Commissions and spread are folded; once opened, the backend's values and their help show.
  const create = page.locator('form').filter({ has: page.getByLabel('Capital inicial') });
  await expect(create.getByLabel('Spread pb')).toBeHidden();
  await create.getByText('Opciones avanzadas').click();
  await expect(create.getByLabel('Spread pb')).toHaveValue(String(defaults.simulation.spread_bps));
  await create.getByRole('button', { name: 'Ayuda: Spread pb' }).hover();
  await expect(page.getByRole('tooltip').filter({ hasText: 'Puntos básicos' })).toBeVisible();
  // The open state is remembered in this browser.
  await page.reload();
  await page.getByText('Crear cartera simulada').click();
  await expect(create.getByLabel('Spread pb')).toBeVisible();
});

test('Inicio muestra la franja macro de la caché y el panel declara frecuencia y agregación (#195)', async ({
  page,
}) => {
  await page.goto('/');
  const strip = page.getByRole('region', { name: 'Contexto macro' });
  await expect(strip).toContainText('Treasury 10 años');
  await expect(strip).toContainText('Curva de tipos (10A-2A)');
  await expect(strip).toContainText('Diaria · último valor publicado');
  await expect(strip).not.toContainText('Fed Funds');
  await strip.getByRole('link', { name: 'Ver panel macro' }).click();
  await expect(page.getByRole('heading', { name: 'Panel macro' })).toBeVisible();
  await expect(page.getByText('FRED FEDFUNDS · Mensual · media del mes')).toBeVisible();
  await expect(page.getByText('FRED WALCL · Semanal · saldo de cada miércoles')).toBeVisible();
  await expect(page.getByText(/no es alcista por sí mismo/)).toBeVisible();
});

test('Perfil y benchmark guarda revisiones y no descarga precios al consultar', async ({
  page,
}) => {
  await page.goto('/cartera/perfil');
  await expect(page.getByRole('heading', { name: 'Perfil y benchmark', level: 1 })).toBeVisible();
  await expect(page.getByText('Guarda tu perfil para ver tu plan')).toBeVisible();
  const form = page.getByRole('form', { name: 'Perfil de inversor' });
  await form.getByLabel('Aportación mensual (€)').fill('500');
  await form.getByRole('button', { name: 'Guardar perfil' }).click();
  await expect(form.getByRole('status')).toContainText('revisión');
  // The test cache has SPY but no EUR rate: the page says so instead of downloading it.
  const plan = page.getByRole('region', { name: 'Tu plan en el S&P 500' });
  await expect(plan).toContainText('USDEUR=X');
  await expect(plan.getByRole('button', { name: 'Actualizar benchmark' })).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole('form', { name: 'Perfil de inversor' }).getByLabel('Aportación mensual (€)'),
  ).toHaveValue('500');
});
