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
    failure:
      status === 'failed'
        ? {
            category: 'interrupted',
            label: 'Trabajo interrumpido',
            message: 'El proceso que ejecutaba el trabajo se detuvo (cierre de GABI o del equipo).',
            action: 'Reintenta cuando GABI vuelva a estar en marcha.',
            retry: 'now',
          }
        : null,
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
  await expect(original.getByText('Trabajo interrumpido')).toBeVisible();
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
  await expect(original.getByText('Trabajo interrumpido')).toBeVisible();
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

test('un fallo imprevisto indica su traza local y los trabajos terminados no repiten el estado', async ({
  page,
}) => {
  const traced = {
    ...job('d'.repeat(32), 'portfolio_lab', 'failed', 'job_failed'),
    phase: 'Fallido',
    diagnostic: true,
  };
  const done = { ...job('e'.repeat(32), 'refresh', 'succeeded'), phase: 'Completado' };
  await page.route('**/api/v1/jobs', (route) => route.fulfill({ json: { jobs: [traced, done] } }));
  await page.goto('/administracion');
  const failed = page.locator('#job-' + traced.id);
  await expect(failed.getByText(`jobs/logs/${traced.id}.log`, { exact: false })).toBeVisible();
  await expect(failed.getByText('Fallido', { exact: true })).toHaveCount(1);
  const finished = page.locator('#job-' + done.id);
  await expect(finished.getByText('Actualización completa', { exact: true })).toBeVisible();
  await expect(finished.getByText('Completado', { exact: true })).toHaveCount(1);
});

test('cada trabajo fallido dice su causa, su último paso y qué hacer; el historial se pliega (#179)', async ({
  page,
}) => {
  const failed = (id: string, kind: string, failure: JobResponse['failure'], last: string) => ({
    ...job(id.repeat(32), kind, 'failed', failure?.category ?? null),
    failure,
    last_activity: last,
  });
  const jobs = [
    failed(
      '1',
      'refresh',
      {
        category: 'rate_limited',
        label: 'Límite de peticiones',
        message: 'La fuente limitó el número de peticiones.',
        action: 'Espera al menos una hora antes de reintentar.',
        retry: 'later',
      },
      'Descargando precios de Yahoo',
    ),
    failed(
      '2',
      'quality',
      {
        category: 'key_missing',
        label: 'Falta una clave',
        message: 'La fuente necesita una clave de acceso que no está guardada en este equipo.',
        action: 'Guarda la clave en Administración → Claves y vuelve a intentarlo.',
        retry: 'after_fix',
      },
      'Leyendo FRED',
    ),
    ...['3', '4', '5', '6', '7'].map((id) => job(id.repeat(32), 'quality', 'succeeded')),
  ];
  await page.route('**/api/v1/jobs', (route) => route.fulfill({ json: { jobs } }));
  await page.goto('/administracion');
  const limited = page.locator('#job-' + '1'.repeat(32));
  await expect(limited.getByText('Límite de peticiones')).toBeVisible();
  await expect(limited).toContainText('Último paso antes del fallo: Descargando precios de Yahoo');
  await expect(limited).toContainText('Qué hacer: Espera al menos una hora antes de reintentar.');
  await expect(page.locator('#job-' + '2'.repeat(32))).toContainText('Falta una clave');
  await expect(page.locator('[id^="job-"]')).toHaveCount(5);
  await page.getByRole('button', { name: 'Ver todos (7)' }).click();
  await expect(page.locator('[id^="job-"]')).toHaveCount(7);
  await page.getByRole('button', { name: 'Ver solo los últimos 5' }).click();
  await expect(page.locator('[id^="job-"]')).toHaveCount(5);
});
