import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  CompanyRow,
  ComparisonResponse,
  DataResponse,
  ModelResponse,
} from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({
  getComparison: vi.fn(),
  getComparisonChecklist: vi.fn(),
  getComparisonPrices: vi.fn(),
  getRiskWindows: vi.fn(),
  getRanking: vi.fn(),
}));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  getComparison: api.getComparison,
  getComparisonChecklist: api.getComparisonChecklist,
  getComparisonPrices: api.getComparisonPrices,
  getRiskWindows: api.getRiskWindows,
  getRanking: api.getRanking,
}));
const { ComparisonPage } = await import('../src/features/market/comparison-page');

function company(symbol: string, marketCap: number): CompanyRow {
  return {
    symbol,
    name: symbol + ' Corp',
    rank: 1,
    sector: null,
    filings: [],
    golden_cross_recent: null,
    next_earnings: null,
    metrics: {
      market_cap: { value: marketCap, unit: 'USD' },
      price: { value: 123.45, unit: 'USD' },
    },
  } as unknown as CompanyRow;
}

let screen: ReturnType<typeof renderScreen> | undefined;
beforeEach(() => {
  api.getRiskWindows.mockReturnValue(new Promise(() => undefined));
});
afterEach(() => screen?.unmount());

describe('Comparar (#173)', () => {
  beforeEach(() => {
    api.getComparisonChecklist.mockReturnValue(new Promise(() => undefined));
    api.getComparisonPrices.mockReturnValue(new Promise(() => undefined));
  });
  it('muestra la capitalización en el formato compacto del Ranking', async () => {
    api.getRanking.mockResolvedValue({ items: [] });
    api.getComparison.mockResolvedValue({
      items: [company('ALL', 1e11), company('TRV', 63_477_456_896)],
      positions: {},
      metric_sources: { market_cap: { source: 'yahoo', period: 'snapshot' } },
      model: { independent_advantage_demonstrated: false } as ModelResponse,
      data: { status: 'ready', warnings: [] } as unknown as DataResponse,
    } as unknown as ComparisonResponse);
    screen = renderScreen(<ComparisonPage />, '/descubrir/comparar?symbols=ALL&symbols=TRV');
    await screen.findText('100 mil M US$');
    expect(screen.text()).toContain('63,48 mil M US$');
    expect(screen.text()).not.toContain('100.000.000.000');
    expect(screen.text()).not.toContain('63.477.456.896');
    // The share price keeps its cents.
    expect(screen.text()).toContain('123,45');
    // Source and period of each value, as the backend declares them (#169).
    expect(screen.text()).toContain('Yahoo · dato actual');
  });
});

describe('Comparar por secciones (#194)', () => {
  it('muestra las secciones, el checklist de cada ficha y el precio en base 100 con SPY', async () => {
    api.getRanking.mockResolvedValue({ items: [] });
    api.getComparison.mockResolvedValue({
      items: [company('ALL', 1e11), company('TRV', 6e10)],
      positions: {},
      metric_sources: {},
      model: { independent_advantage_demonstrated: false } as ModelResponse,
      data: { status: 'ready', warnings: [] } as unknown as DataResponse,
    } as unknown as ComparisonResponse);
    const median = { median: 14.5, count: 30, reason: null };
    const digest = (symbol: string, passed: number, alarms: string[]) => ({
      symbol,
      fiscal_year_end: '2025-12-31',
      financial_sector: true,
      summary: { passed, evaluated: 10, missing: 2 },
      criteria: [
        {
          key: 'pe',
          label: 'PER',
          unit: 'ratio',
          value: 12.3,
          threshold: 18,
          comparison: '<=',
          verdict: 'pass',
          reason: null,
          source: 'price+sec',
          period: 'fiscal_year',
        },
      ],
      active_alarms: alarms,
      history_medians: { pe: { median: 11, count: 5, reason: null } },
      history_years: 5,
      sector: 'Financials',
      sector_peers: 30,
      sector_reason: null,
      sector_medians: { pe: median },
    });
    api.getComparisonChecklist.mockResolvedValue({
      items: [digest('ALL', 7, []), digest('TRV', 4, ['Goodwill elevado'])],
      revision: 'r',
    });
    api.getComparisonPrices.mockResolvedValue({
      symbols: ['ALL', 'TRV'],
      benchmark: 'SPY',
      base_date: '2025-10-01',
      bars: 252,
      points: [
        { date: '2025-10-01', values: { ALL: 100, TRV: 100, SPY: 100 } },
        { date: '2025-10-02', values: { ALL: 104.25, TRV: 98, SPY: null } },
      ],
      unit: 'index_100',
      source: 'local_cache_yahoo',
      revision: 'r',
    });
    screen = renderScreen(<ComparisonPage />, '/descubrir/comparar?symbols=ALL&symbols=TRV');
    await screen.findText('7 de 10 cumplidos');
    const text = screen.text();
    for (const title of [
      'Score y bloques',
      'Valoración',
      'Calidad y salud',
      'Riesgo',
      'Catalizadores',
    ])
      expect(text).toContain(title);
    expect(text).toContain('4 de 10 cumplidos');
    expect(text).toContain('Goodwill elevado');
    expect(text).toContain('Propia: 11x (5 años) · Sector: 14,5x (30 pares)');
    await screen.findText('ALL: 104,3');
    expect(screen.text()).toContain('SPY: —');
    expect(api.getComparisonPrices).toHaveBeenCalledWith(['ALL', 'TRV'], 252, expect.anything());
  });
});
