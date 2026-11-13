import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HeatmapResponse } from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({ getHeatmap: vi.fn() }));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { HeatmapPage } = await import('../src/features/market/heatmap-page');

const DATA = {
  model_id: 'GABI-MF-v3',
  generated_at: '2026-11-05T10:00:00Z',
  data: {
    status: 'ready',
    universe_count: 3,
    prices_available: 3,
    fundamentals_available: 3,
    sec_available: 3,
    scored_count: 2,
    latest_price_date: '2026-11-04',
    warnings: [],
    last_session: '2026-11-04',
    prices_current: true,
  },
  companies: [
    {
      symbol: 'AAA',
      name: 'Alpha',
      sector: 'Tech',
      market_cap: 3e12,
      composite_score: 85,
      rank: 1,
      band: 'very_high',
      reason: null,
    },
    {
      symbol: 'BBB',
      name: 'Beta',
      sector: 'Tech',
      market_cap: 1e11,
      composite_score: 35,
      rank: 2,
      band: 'low',
      reason: null,
    },
    {
      symbol: 'CCC',
      name: 'Gamma',
      sector: 'Health',
      market_cap: null,
      composite_score: null,
      rank: null,
      band: 'none',
      reason: 'Sin puntuación: le faltan datos de su precio o de sus cuentas para calcularla.',
    },
  ],
  sectors: [
    { sector: 'Tech', companies: 2, scored: 2, mean_score: 60, in_top: 1, market_cap: 3.1e12 },
    { sector: 'Health', companies: 1, scored: 0, mean_score: null, in_top: 0, market_cap: null },
  ],
  scored: 2,
  top_count: 1,
  top_share: 0.2,
  bands: [
    { band: 'very_high', min_score: 80 },
    { band: 'high', min_score: 70 },
    { band: 'medium', min_score: 40 },
    { band: 'low', min_score: 30 },
    { band: 'very_low', min_score: null },
  ],
} as unknown as HeatmapResponse;

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

describe('Mapa del mercado (#311)', () => {
  it('explica los colores, lista por sectores y nombra lo que no se puede dibujar', async () => {
    api.getHeatmap.mockResolvedValue(DATA);
    screen = renderScreen(<HeatmapPage />);
    await screen.findText('80 o más');
    const text = screen.text();
    expect(text).toContain('70–80');
    expect(text).toContain('menos de 30');
    expect(text).toContain('sin puntuación');
    expect(text).toContain('2 de 3 empresas tienen puntuación.');
    expect(text).toContain(
      '1 no aparece en el mapa porque no está guardado su valor en bolsa: CCC (está en la lista).',
    );
    expect(text).toContain('Tech · 2 empresas · puntuación media 60 · 1 entre las mejores');
    expect(text).toContain('Health · 1 empresa · puntuación media sin dato');
  });
});
