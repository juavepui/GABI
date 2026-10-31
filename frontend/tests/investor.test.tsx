import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  BenchmarkPerformance,
  InvestorBenchmarkResult,
  InvestorProfileState,
} from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({
  getInvestorProfile: vi.fn(),
  getInvestorBenchmark: vi.fn(),
  getHoldingsBenchmark: vi.fn(),
  getJobs: vi.fn(),
}));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { ApiError } = await import('../src/shared/api/client');
const { InvestorPage } = await import('../src/features/portfolio/investor-page');

const profile = {
  initial_eur: 11000,
  monthly_eur: 700,
  horizon_months: 24,
  loss_tolerance: 0.2,
  capital_needed_by: '2027-03-01',
  tax_residence: null,
  commission_fixed_eur: 1,
  commission_pct: 0,
  fx_cost_pct: 0.006,
  min_order_eur: 0,
  fractional: true,
};
const saved: InvestorProfileState = {
  current: {
    revision: 2,
    version: 'investor-profile-v1',
    created_at: '2026-10-31T08:00:00Z',
    profile,
  },
  revisions: [],
};
const performance: BenchmarkPerformance = {
  status: 'ok',
  start: '2024-10-31',
  end: '2026-10-30',
  contributed_eur: 27100,
  final_value_eur: 30000,
  costs_eur: 190,
  pending_eur: 0,
  twr: 0.25,
  twr_annualised: 0.118,
  xirr: 0.1,
  max_drawdown: -0.22,
  current_drawdown: 0,
  max_loss_on_contributions: -0.05,
  max_euros_lost: -900,
  euros_at_risk_at_tolerance: 6000,
  review_threshold_reached_on: '2025-04-08',
};
const benchmark: InvestorBenchmarkResult = {
  as_of: '2026-10-31',
  start: '2024-10-31',
  profile_revision: 2,
  profile_version: 'investor-profile-v1',
  capital_need_before_horizon: true,
  source: {
    symbol: 'SPY',
    series: 'adj_close',
    provider: 'yahoo',
    vehicle: 'SPDR S&P 500 ETF.',
    fx: 'USDEUR=X',
    first_price: '2024-10-31',
    last_price: '2026-10-30',
    first_fx: '2024-10-31',
    last_fx: '2026-10-30',
  },
  performance,
  pending: [],
  series: [],
};

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => {
  screen?.unmount();
  vi.clearAllMocks();
});

describe('Perfil y benchmark (#244)', () => {
  it('sin perfil propone valores y no consulta el benchmark', async () => {
    api.getInvestorProfile.mockResolvedValue({ current: null, revisions: [] });
    screen = renderScreen(<InvestorPage />);
    await screen.findText('Guarda tu perfil para ver tu plan');
    expect(api.getInvestorBenchmark).not.toHaveBeenCalled();
    const tolerance = screen.container.querySelector<HTMLInputElement>('[name=loss_tolerance]');
    expect(tolerance?.value).toBe('20');
  });

  it('muestra habilidad, experiencia, el umbral de revisión y el aviso de plazo', async () => {
    api.getInvestorProfile.mockResolvedValue(saved);
    api.getInvestorBenchmark.mockResolvedValue(benchmark);
    api.getHoldingsBenchmark.mockRejectedValue(
      new ApiError(404, 'no_holdings', 'Mi cartera no tiene compras que comparar.'),
    );
    screen = renderScreen(<InvestorPage />);
    await screen.findText('Necesitas el dinero antes de terminar el horizonte');
    expect(screen.text()).toContain('TWR+25 %');
    expect(screen.text()).toContain('El 2025-04-08; revisar, no vender por sí solo');
    expect(screen.text()).toContain('Todavía no has registrado compras.');
    const fx = screen.container.querySelector<HTMLInputElement>('[name=fx_cost_pct]');
    expect(fx?.value).toBe('0.6');
  });

  it('sin precios en caché explica cómo actualizarlos', async () => {
    api.getInvestorProfile.mockResolvedValue(saved);
    api.getInvestorBenchmark.mockRejectedValue(
      new ApiError(409, 'benchmark_prices_missing', 'Faltan precios en caché de SPY.'),
    );
    api.getHoldingsBenchmark.mockRejectedValue(
      new ApiError(404, 'no_holdings', 'Mi cartera no tiene compras que comparar.'),
    );
    screen = renderScreen(<InvestorPage />);
    await screen.findText('Faltan precios en caché de SPY.');
    expect(screen.text()).toContain('Actualizar benchmark');
  });
});
