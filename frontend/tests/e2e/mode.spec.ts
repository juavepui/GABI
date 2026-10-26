import { expect, test, type Page } from '@playwright/test';

const MODE = 'http://127.0.0.1:8001/api/v1/administration/mode';
const setMode = (page: Page, mode: 'INVESTOR' | 'RESEARCH') =>
  page.request.post(MODE, { data: { mode } });
test.afterEach(async ({ page }) => {
  await setMode(page, 'INVESTOR');
});

const menu = (page: Page) => page.getByRole('navigation', { name: 'Navegación principal' });

test('modo Investor: sin Investigación ni parámetros de experimento (#189)', async ({ page }) => {
  await page.goto('/');
  await expect(menu(page).getByRole('link', { name: 'Cartera' })).toBeVisible();
  await expect(menu(page).getByRole('link', { name: 'Investigación' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Modo Investor' })).toBeVisible();

  // By URL, the page explains why and leads to the mode selector.
  await page.goto('/investigacion/carteras');
  await expect(
    page.getByRole('heading', { name: 'Investigación está en el modo Research', level: 1 }),
  ).toBeVisible();
  await expect(page.getByRole('list', { name: 'Apartados de Investigación' })).toHaveCount(0);
  await page.getByRole('main').getByRole('link', { name: 'Activar el modo Research' }).click();
  await expect(page).toHaveURL(/\/administracion#modo$/);
  await expect(page.locator('#modo')).toContainText('Modo de trabajo · Investor');
  await expect(page.getByRole('button', { name: 'Activar Research' })).toBeInViewport();
  await expect(page.getByRole('heading', { name: /^Pesos del modelo/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Investigación exploratoria' })).toHaveCount(0);

  await page.goto('/cartera?plan=experimental');
  await expect(page.getByText('Se usa la política por defecto')).toBeVisible();
  await expect(page.getByLabel('Score mínimo')).toHaveCount(0);
});

test('modo Research: todo visible y el indicador lleva a cambiar de modo (#189)', async ({
  page,
}) => {
  await setMode(page, 'RESEARCH');
  await page.goto('/');
  await menu(page).getByRole('link', { name: 'Investigación' }).click();
  await expect(page.getByRole('heading', { name: 'Investigación', level: 1 })).toBeVisible();

  await page.goto('/cartera?plan=experimental');
  await expect(page.getByLabel('Score mínimo')).toBeVisible();
  await expect(page.getByText('Se usa la política por defecto')).toHaveCount(0);

  await page.getByRole('link', { name: 'Modo Research' }).click();
  await expect(page).toHaveURL(/\/administracion#modo$/);
  await expect(page.getByRole('heading', { name: /^Pesos del modelo/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Investigación exploratoria' })).toBeVisible();
});
