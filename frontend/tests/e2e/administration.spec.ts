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

test('calidad de los datos: universo, procedencia, identidades y archivo desde 2010', async ({
  page,
}) => {
  await page.goto('/administracion');
  await page
    .getByRole('main')
    .getByRole('link', { name: /Calidad de los datos/ })
    .click();
  await expect(page.getByRole('heading', { name: 'Calidad de los datos', level: 1 })).toBeVisible();

  const universe = page.getByRole('region', { name: 'Resumen del universo' });
  await universe.getByRole('button', { name: 'Comprobar calidad del universo' }).click();
  const sources = universe.getByRole('table', { name: 'Cobertura y frescura por fuente' });
  await expect(sources.getByText('Precios (Yahoo)')).toBeVisible({ timeout: 15_000 });
  await expect(sources.getByText('100 % (2/2)').first()).toBeVisible();
  await expect(universe.getByText('Sector point-in-time aproximado.')).toBeVisible();
  await universe.getByText('1 fallos de actualización en los últimos 7 días').click();
  await expect(universe.getByRole('table', { name: 'Fallos recientes' })).toContainText(
    'sin precio',
  );

  const company = page.getByRole('region', { name: 'Procedencia de una empresa' });
  await company.getByRole('combobox', { name: 'Empresa' }).fill('T000');
  await company.getByLabel('Fecha de referencia del sector point-in-time').fill('2026-09-28');
  await company.getByRole('button', { name: 'Ver procedencia' }).click();
  const provenance = company.getByRole('table', { name: 'Procedencia por fuente' });
  await expect(provenance.getByText('250 sesiones, última: 2026-09-28')).toBeVisible({
    timeout: 15_000,
  });
  await expect(provenance.getByText('Aproximado')).toBeVisible();
  await company.getByText('Diagnóstico de identidad del universo').click();
  await company.getByRole('button', { name: /Comprobar identidades/ }).click();
  await expect(company.getByText(/1 símbolos sin CIK acreditado/)).toBeVisible({ timeout: 15_000 });

  const archive = page.getByRole('region', { name: 'Archivo histórico 2010-2015' });
  await archive.getByRole('button', { name: 'Consultar cobertura del archivo' }).click();
  await expect(archive.getByRole('table', { name: 'Fuentes del archivo' })).toBeVisible({
    timeout: 15_000,
  });
  await expect(archive.getByLabel('Fecha de composición archivada')).toHaveAttribute(
    'min',
    '2010-01-01',
  );
  await archive.getByRole('button', { name: 'Ver miembros del índice' }).click();
  await expect(
    archive.getByText(/2 valores en la composición registrada el 2010-01-04/),
  ).toBeVisible({
    timeout: 15_000,
  });
  await archive.getByRole('button', { name: 'Ver precios del archivo' }).click();
  await archive.getByText('1 sesiones de ATVI').click();
  await expect(archive.getByRole('table', { name: 'Precios archivados' })).toContainText('9.5');
  await archive.getByText('Cobertura trimestral 2010-2015').click();
  const quarterly = archive.getByRole('table', { name: 'Cobertura trimestral' });
  await expect(quarterly).toContainText('2010-03-31');
  await expect(quarterly).not.toContainText('2009-12-31');

  await page.reload();
  await expect(
    page.getByRole('table', { name: 'Cobertura y frescura por fuente' }).getByText('SEC EDGAR'),
  ).toBeVisible({ timeout: 15_000 });
});

test('el indicador de la cabecera sigue un trabajo y avisa al terminar en otra pantalla', async ({
  page,
}) => {
  await page.goto('/administracion');
  const update = page.getByRole('region', { name: 'Actualizar datos' });
  await update.getByRole('button', { name: 'Actualizar datos' }).click();
  // Leave the page that launched it: the header keeps track of the job.
  await page.getByRole('link', { name: 'Mercado', exact: true }).first().click();
  const toast = page.getByRole('status', { name: 'Avisos de trabajos' });
  await expect(toast.getByText('Actualizar datos (Yahoo y SEC)')).toBeVisible({ timeout: 15_000 });
  await expect(toast.getByText(/Completado/)).toBeVisible();
  await page.getByRole('button', { name: /^Trabajos:/ }).click();
  const panel = page.getByRole('region', { name: 'Trabajos locales' });
  await expect(panel.getByText('Recientes')).toBeVisible();
  await expect(panel.getByText('Actualizar datos (Yahoo y SEC)').first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await toast.getByRole('button', { name: 'Cerrar aviso' }).first().click();
  await expect(toast.getByText('Actualizar datos (Yahoo y SEC)')).toHaveCount(0);
});

test('botones, campos y desplegables comparten tamaño de letra y altura', async ({ page }) => {
  await page.goto('/administracion');
  await expect(page.getByRole('heading', { name: 'Administración' })).toBeVisible();
  const sizes = await page.evaluate(() => {
    const read = (selector: string) =>
      [...document.querySelectorAll<HTMLElement>(`main ${selector}`)].map((element) => ({
        font: getComputedStyle(element).fontSize,
        height: Math.round(element.getBoundingClientRect().height),
      }));
    return {
      buttons: read('[data-slot="button"][data-size="default"]'),
      selects: read('[data-slot="native-select"]'),
    };
  });
  expect(sizes.buttons.length).toBeGreaterThan(3);
  expect(new Set(sizes.buttons.map((size) => size.font))).toEqual(new Set(['14px']));
  expect(new Set(sizes.buttons.map((size) => size.height))).toEqual(new Set([36]));
  expect(new Set(sizes.selects.map((size) => size.font))).toEqual(new Set(['14px']));
});
