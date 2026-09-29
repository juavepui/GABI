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
