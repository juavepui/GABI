import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  CompanyRow,
  ComparisonResponse,
  DataResponse,
  ModelResponse,
} from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({ getComparison: vi.fn(), getRanking: vi.fn() }));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  getComparison: api.getComparison,
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
afterEach(() => screen?.unmount());

describe('Comparar (#173)', () => {
  it('muestra la capitalización en el formato compacto del Ranking', async () => {
    api.getRanking.mockResolvedValue({ items: [] });
    api.getComparison.mockResolvedValue({
      items: [company('ALL', 1e11), company('TRV', 63_477_456_896)],
      positions: {},
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
  });
});
