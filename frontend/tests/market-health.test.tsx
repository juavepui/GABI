import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MarketHealthResponse } from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({ getMarketHealth: vi.fn() }));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { MarketHealthCard } = await import('../src/features/market/market-health');

const READY: MarketHealthResponse = {
  status: 'ready',
  version: 'market-health-v1',
  benchmark: 'SPY',
  universe_count: 503,
  affects_score: false,
  as_of: '2026-11-04',
  score: 66.67,
  state: 'pressure',
  state_label: 'Con presión',
  days_in_state: 8,
  days_at_least: false,
  history_sessions: 120,
  checks: [
    {
      key: 'distribution',
      result: 'fail',
      title: 'Jornadas de ventas fuertes',
      text: '6 jornadas de ventas fuertes en las últimas 25 sesiones.',
      values: { heavy_days: 6, window: 25 },
    },
    {
      key: 'volatility',
      result: null,
      title: 'Nerviosismo (VIX)',
      text: 'Sin dato del VIX: llega con los datos de FRED en la próxima actualización.',
      values: { vix: null },
    },
  ],
};

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

describe('Semáforo del mercado (#308)', () => {
  it('enseña el estado, los días, cada comprobación y el aviso de que no predice', async () => {
    api.getMarketHealth.mockResolvedValue(READY);
    screen = renderScreen(<MarketHealthCard />);
    await screen.findText('Con presión');
    const text = screen.text();
    expect(text).toContain('67 de 100');
    expect(text).toContain('8 sesiones en este estado');
    expect(text).toContain('6 jornadas de ventas fuertes en las últimas 25 sesiones.');
    expect(text).toContain('Falla');
    expect(text).toContain('Sin dato');
    expect(text).toContain('no predice lo que hará');
  });

  it('explica qué falta si no hay historia suficiente del índice', async () => {
    api.getMarketHealth.mockResolvedValue({
      status: 'no_data',
      version: 'market-health-v1',
      benchmark: 'SPY',
      universe_count: 0,
      affects_score: false,
      sessions: 0,
      checks: [],
    });
    screen = renderScreen(<MarketHealthCard />);
    await screen.findText('Sin datos suficientes');
    expect(screen.text()).toContain('201 días de bolsa');
  });
});
