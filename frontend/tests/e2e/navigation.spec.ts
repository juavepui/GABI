import { expect, test } from '@playwright/test';

test('el menú se organiza por tareas y la Ayuda está en la cabecera (#188)', async ({ page }) => {
  await page.goto('/');
  const menu = page.getByRole('navigation', { name: 'Navegación principal' });
  // Section links only; the pages of the active section are listed under it.
  await expect(menu.locator(':scope > div > a')).toHaveText([
    'Hoy',
    'Descubrir',
    'Cartera',
    'Administración',
  ]);
  await expect(page.getByRole('list', { name: 'Apartados de Hoy' })).toContainText('Panel macro');
  await page.getByRole('banner').getByRole('link', { name: 'Ayuda y glosario' }).click();
  await expect(page).toHaveURL(/\/ayuda$/);
  await expect(page).toHaveTitle('Ayuda · GABI');
});

test('el buscador de la cabecera lleva a la ficha desde cualquier página (#188)', async ({
  page,
}) => {
  await page.goto('/administracion');
  const search = page.getByRole('search').getByRole('combobox', { name: 'Buscar empresa' });
  await search.fill('001');
  await page.getByRole('option', { name: /T001/ }).click();
  await expect(page).toHaveURL(/\/empresas\/T001$/);
  await expect(page.getByRole('heading', { name: 'Company T001', exact: true })).toBeVisible();
  await expect(
    page.getByRole('navigation', { name: 'Navegación principal' }).getByRole('link', {
      name: 'Descubrir',
    }),
  ).toHaveAttribute('aria-current', 'page');
});

test('las rutas antiguas redirigen conservando consulta y ancla (#188)', async ({ page }) => {
  const cases: [string, RegExp][] = [
    ['/mercado?order_by=market_cap&limit=10', /\/descubrir\?order_by=market_cap&limit=10$/],
    [
      '/mercado/comparar?symbols=T000&symbols=T001',
      /\/descubrir\/comparar\?symbols=T000&symbols=T001$/,
    ],
    ['/mercado/empresas/T001', /\/empresas\/T001$/],
    ['/mercado/macro', /\/macro$/],
    ['/mercado/senales', /\/cartera\/seguimiento$/],
    ['/cartera/aprender?tab=glosario#termino-per', /\/ayuda\?tab=glosario#termino-per$/],
    ['/cartera/decisiones', /\/cartera\?plan=experimental$/],
  ];
  for (const [from, to] of cases) {
    await page.goto(from);
    await expect(page, from).toHaveURL(to);
    await expect(page.locator('main h1'), from).toBeVisible();
  }
});
