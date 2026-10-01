import { expect, test } from '@playwright/test';

test('un job local sigue después de recargar y publica un resultado verificable', async ({
  page,
}, testInfo) => {
  await page.goto('/administracion');
  await expect(page.getByRole('heading', { name: 'Administración' })).toBeVisible();
  await expect(page.getByText('Investor, bloqueados')).toBeVisible();
  await expect(page.getByLabel('Valor (%)')).toBeDisabled();
  const mobile = testInfo.project.name === 'mobile';
  const name = mobile ? 'Descargar símbolos indicados' : 'Auditar cobertura local';
  if (mobile) {
    await page.getByLabel('Descargar símbolos concretos').fill('SPY');
    await page.getByRole('button', { name: 'Solicitar' }).click();
  } else {
    await page.getByRole('button', { name: 'Auditar cobertura' }).click();
  }
  await expect(page.getByRole('listitem', { name })).toBeVisible();
  await page.reload();
  const job = page.getByRole('listitem', { name });
  await expect(job.locator('span').getByText('Completado')).toBeVisible({ timeout: 15_000 });
  await job.getByRole('button', { name: 'Ver actividad' }).click();
  await expect(job.getByText('Trabajo encolado')).toBeVisible();
  await job.getByRole('button', { name: 'Ver resultado' }).click();
  await expect(page.getByText('Resultado verificado')).toBeVisible();
  if (mobile) await expect(page.getByText('"fixture": true')).toBeVisible();
  else
    await expect(
      page.getByRole('list', { name: 'Cobertura por fuente' }).getByText('2/2'),
    ).toBeVisible();
});

test('actualizar datos resume los fallos, reintenta los fallidos y guarda claves', async ({
  page,
}) => {
  await page.goto('/administracion');
  const update = page.getByRole('region', { name: 'Actualizar datos' });
  await update.getByRole('combobox', { name: 'Tamaño del universo' }).selectOption('150');
  await update.getByRole('button', { name: 'Actualizar datos' }).click();
  const result = update.getByRole('region', { name: 'Resultado de la actualización' });
  await expect(result.getByText(/Actualización de 3 empresas/)).toBeVisible({ timeout: 15_000 });
  await expect(result.getByText(/empresas con fallos: 1/)).toBeVisible();
  await result.getByText('límite de peticiones — 1 empresas').click();
  await expect(result.getByText('T001', { exact: true })).toBeVisible();
  await result.getByRole('button', { name: 'Reintentar solo los fallidos' }).click();
  await expect(result.getByText(/Reintento de 1 empresas/)).toBeVisible({ timeout: 15_000 });
  await expect(result.getByText('Ninguna empresa ha fallado en esta actualización.')).toBeVisible();

  const fred = page.getByRole('form', { name: 'Clave FRED (panel macro)' });
  await fred.getByLabel('Nueva clave FRED (panel macro)').fill('clave-e2e');
  await fred.getByRole('button', { name: 'Guardar' }).click();
  await expect(fred.getByText('Clave guardada.')).toBeVisible();
  await expect(fred.getByText('Configurada')).toBeVisible();
  await expect(page.getByText('clave-e2e')).toHaveCount(0);
});
