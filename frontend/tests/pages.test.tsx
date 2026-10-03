import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RankingResponse } from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({
  getRanking: vi.fn(),
  getSimulations: vi.fn(),
  getRankingCoverage: vi.fn(),
  getJobs: vi.fn(),
}));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { ApiError } = await import('../src/shared/api/client');
const { MarketPage } = await import('../src/features/market/market-page');
const { SimulationsPage } = await import('../src/features/portfolio/simulations-page');
const { DataHealthPage } = await import('../src/features/administration/data-health-page');

const emptyRanking = {
  items: [],
  total: 0,
  offset: 0,
  limit: 25,
  sectors: [],
  model: {
    mode: 'INVESTOR',
    model_id: 'GABI-MF-v1',
    status: 'FROZEN',
    weights: {},
    weights_unit: 'fraction',
    matches_frozen: true,
    live_forward_source: null,
    blind_validation_id: null,
    independent_advantage_demonstrated: false,
    evidence_note: '',
  },
  data: {
    status: 'empty',
    universe_count: 0,
    prices_available: 0,
    fundamentals_available: 0,
    sec_available: 0,
    scored_count: 0,
    latest_price_date: null,
    warnings: [],
  },
  generated_at: '2026-10-03T08:00:00Z',
  universe_cached_at: null,
  revision: 'r',
  cache_hit: false,
  risk_free_rate: { value: null, unit: 'fraction' },
} as unknown as RankingResponse;

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

describe('estados vacío y de error de las páginas grandes', () => {
  it('Mercado: una caché sin empresas lleva a Administración', async () => {
    api.getRanking.mockResolvedValue(emptyRanking);
    screen = renderScreen(<MarketPage />, '/mercado');
    await screen.findText('La caché local no contiene empresas');
    expect(screen.text()).toContain('Ir a Administración');
  });

  it('Mercado: el error de la API se muestra con su mensaje', async () => {
    api.getRanking.mockRejectedValue(new ApiError(503, 'busy', 'El ranking se está calculando.'));
    screen = renderScreen(<MarketPage />, '/mercado');
    await screen.findText('No se pueden cargar los datos');
    expect(screen.text()).toContain('El ranking se está calculando.');
  });

  it('Carteras simuladas: sin carteras invita a crear una', async () => {
    api.getSimulations.mockResolvedValue({ items: [] });
    screen = renderScreen(<SimulationsPage />, '/cartera/simuladas');
    await screen.findText('Crea una cartera para empezar.');
    expect(screen.text()).not.toContain('Comparar carteras');
  });

  it('Carteras simuladas: el error de la API no deja la pantalla en blanco', async () => {
    api.getSimulations.mockRejectedValue(new ApiError(500, 'internal', 'Base local bloqueada.'));
    screen = renderScreen(<SimulationsPage />, '/cartera/simuladas');
    await screen.findText('Base local bloqueada.');
    expect(screen.text()).toContain('Reintentar');
  });

  it('Calidad de los datos: el error de la cobertura por bloques se explica', async () => {
    api.getJobs.mockResolvedValue({ jobs: [] });
    api.getRankingCoverage.mockRejectedValue(
      new ApiError(500, 'internal', 'No se puede leer la cobertura.'),
    );
    screen = renderScreen(<DataHealthPage />, '/administracion/calidad');
    await screen.findText('Calcular cobertura');
    expect(api.getRankingCoverage).not.toHaveBeenCalled(); // A long calculation waits for a click.
    const button = [...screen.container.querySelectorAll('button')].find(
      (element) => element.textContent === 'Calcular cobertura',
    )!;
    act(() => button.click());
    await screen.findText('No se puede leer la cobertura.');
    expect(screen.text()).toContain('Calidad de los datos');
  });
});
