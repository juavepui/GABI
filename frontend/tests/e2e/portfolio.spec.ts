import { expect, test } from '@playwright/test';

test('cartera y diario conservan el plan y las tesis locales', async ({ page }) => {
  await page.goto('/cartera');
  await expect(page.getByRole('heading', { name: 'Mi cartera objetivo' })).toBeVisible();
  await expect(page.getByText('Top-20 congelado')).toBeVisible();
  await page.getByLabel('Posiciones actuales (SÍMBOLO,euros; una por línea)').fill('T000,100');
  await page.getByRole('button', { name: 'Calcular plan' }).click();
  await expect(page.getByRole('heading', { name: 'Dónde aportar capital nuevo' })).toBeVisible();
  await page.getByRole('link', { name: 'Abrir diario de inversión' }).click();
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
});

test('comparación y macro leen los contratos de Mercado', async ({ page }) => {
  await page.goto('/mercado/comparar');
  await page.getByLabel('Empresa 1').selectOption('T000');
  await page.getByLabel('Empresa 2').selectOption('T001');
  await expect(page.getByRole('heading', { name: 'Métricas comparables' })).toBeVisible();
  await expect(page.getByRole('row', { name: /Composite Score/ })).toBeVisible();
  await page.goto('/mercado/macro');
  await expect(page.getByRole('heading', { name: 'Panel macro' })).toBeVisible();
  await expect(page.getByText('Treasury 10 años')).toBeVisible();
  await expect(page.getByText('FRED', { exact: false }).first()).toBeVisible();
});

test('Signal Monitor conserva snapshots y compara sin abrir Streamlit', async ({ page }) => {
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
  await page.getByRole('button', { name: 'Guardar plan' }).click();
  await expect(page.getByText(/Plan #\d+ guardado/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Planes anteriores' })).toBeVisible();
  await expect(page.getByText('Progreso desde el plan')).toBeVisible();
});
