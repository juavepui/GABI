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
  await expect(page.getByRole('row', { name: /T000/ })).toContainText('72,5');
  await expect(page.getByRole('row', { name: /T001/ })).toContainText('unresolved');
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

test('Factor Lab ejecuta un job y presenta el resultado exploratorio', async ({ page }) => {
  await page.request.post('http://127.0.0.1:8001/_test/mode?mode=RESEARCH');
  try {
    await page.goto('/investigacion');
    await page.getByRole('link', { name: 'Abrir Factor Lab' }).click();
    await expect(page.getByRole('heading', { name: 'Factor Lab' })).toBeVisible();
    await page.getByRole('button', { name: 'Ejecutar Factor Lab' }).click();
    await expect(page.getByRole('heading', { name: 'Resumen de factores' })).toBeVisible();
    await expect(page.getByRole('row', { name: /value_score 3 meses/ })).toContainText('0,12');
    await expect(page.getByRole('link', { name: /Descargar series/ })).toBeVisible();
  } finally {
    await page.request.post('http://127.0.0.1:8001/_test/mode?mode=INVESTOR');
  }
});
