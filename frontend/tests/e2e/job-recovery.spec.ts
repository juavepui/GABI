import { expect, test } from '@playwright/test';
import type { JobResponse } from '../../src/shared/api/generated/types.gen';

function job(
  id: string,
  kind: string,
  status: string,
  error_code: string | null = null,
): JobResponse {
  return {
    id,
    kind,
    status,
    error_code,
    origin: 'ui',
    parameters: { symbols: [], start: null, end: null },
    progress: 0,
    phase: status === 'failed' ? 'Interrumpido' : 'En espera',
    cancel_requested: false,
    created_at: '2026-10-15T12:00:00+00:00',
    started_at: null,
    finished_at: null,
    result_ref: null,
    result_sha256: null,
    checkpoint: {},
  };
}

test('repetir un trabajo interrumpido evita doble clic, enlaza el nuevo intento y sobrevive a recargar', async ({
  page,
}) => {
  const source = job('a'.repeat(32), 'refresh', 'failed', 'worker_interrupted');
  const replacement = job('b'.repeat(32), 'refresh', 'queued');
  const restricted = job('c'.repeat(32), 'maintenance', 'failed');
  let jobs = [source, restricted];
  let posts = 0;
  let key = '';
  await page.route('**/api/v1/jobs', (route) => route.fulfill({ json: { jobs } }));
  await page.route('**/api/v1/jobs/*/retry', async (route) => {
    posts++;
    key = route.request().postDataJSON().idempotency_key;
    await new Promise((resolve) => setTimeout(resolve, 200));
    jobs = [replacement, source, restricted];
    await route.fulfill({ status: 202, json: replacement });
  });
  await page.goto('/administracion');
  const original = page.locator('#job-' + source.id);
  await expect(original.getByText(/El worker se interrumpió/)).toBeVisible();
  await expect(original.getByRole('button', { name: 'Ver resultado' })).toHaveCount(0);
  await expect(
    page.locator('#job-' + restricted.id).getByRole('button', { name: 'Solicitar nuevo intento' }),
  ).toHaveCount(0);
  await original.getByRole('button', { name: 'Solicitar nuevo intento' }).dblclick();
  await expect(page.getByRole('link', { name: /Ver nuevo intento/ })).toHaveAttribute(
    'href',
    '#job-' + replacement.id,
  );
  expect(posts).toBe(1);
  expect(key.length).toBeGreaterThanOrEqual(8);
  await page.reload();
  await expect(original.getByText(/El worker se interrumpió/)).toBeVisible();
  await page.getByRole('link', { name: /Ver nuevo intento/ }).click();
  await expect(page.locator('#job-' + replacement.id)).toBeVisible();
  await expect(
    page.locator('#job-' + replacement.id).getByText('En espera', { exact: true }),
  ).toBeVisible();
});

test('una respuesta perdida reutiliza la clave y la cancelación solicitada se distingue de la efectiva', async ({
  page,
}) => {
  const source = job('d'.repeat(32), 'quality', 'cancelled');
  const running = {
    ...job('e'.repeat(32), 'refresh', 'running'),
    progress: 45,
    phase: 'Descargando',
    cancel_requested: true,
  };
  const keys: string[] = [];
  await page.route('**/api/v1/jobs', (route) =>
    route.fulfill({ json: { jobs: [source, running] } }),
  );
  await page.route('**/api/v1/jobs/*/retry', (route) => {
    keys.push(route.request().postDataJSON().idempotency_key);
    return route.fulfill({
      status: 503,
      json: { status: 'error', error: { code: 'unavailable', message: 'Respuesta no disponible' } },
    });
  });
  await page.goto('/administracion');
  const original = page.locator('#job-' + source.id);
  await expect(
    original.getByText('Cancelación completada. No se publicó un resultado.'),
  ).toBeVisible();
  await expect(
    page.getByText(/El trabajo sigue en curso hasta alcanzar un punto seguro/),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancelación solicitada' })).toBeDisabled();
  await original.getByRole('button', { name: 'Solicitar nuevo intento' }).click();
  await expect(page.getByText('Respuesta no disponible')).toBeVisible();
  await page.reload();
  await original.getByRole('button', { name: 'Solicitar nuevo intento' }).click();
  await expect(page.getByText('Respuesta no disponible')).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});
