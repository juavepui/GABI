import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  PolicyProposal,
  PortfolioPolicyState,
  RiskPanel,
} from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({
  getPortfolioPolicy: vi.fn(),
  getRiskPanel: vi.fn(),
  getPolicyProposal: vi.fn(),
}));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { ApiError } = await import('../src/shared/api/client');
const { RiskPage } = await import('../src/features/portfolio/risk-page');

const defaults = {
  max_issuer_weight: 0.1,
  max_sector_weight: 0.3,
  cash_weight: 0,
  min_daily_dollar_volume: 5e6,
  participation: 0.1,
  max_cost_share: 0.01,
};
const policy: PortfolioPolicyState = {
  current: null,
  revisions: [],
  default: defaults,
  version: 'portfolio-policy-v1',
};
const panel: RiskPanel = {
  as_of: '2026-10-31',
  policy_version: 'portfolio-policy-v1',
  policy_revision: null,
  policy: defaults,
  loss_tolerance: 0.2,
  positions: 2,
  unvalued: [],
  exposure: {
    total_eur: 1000,
    issuers: [
      {
        issuer: 'cik:0001067983',
        symbols: ['BRK-A', 'BRK-B'],
        value_eur: 1000,
        weight: 1,
        exceeds: true,
      },
    ],
    sectors: [{ name: 'Financials', weight: 1, exceeds: true }],
    industries: [],
    listing_currency: [{ name: 'USD', weight: 1 }],
    economic_currency: [{ name: 'USD', weight: 1 }],
    factors: { value: { score: 60, coverage: 1 } },
    liquidity: [
      {
        symbol: 'BRK-A',
        value_eur: 500,
        daily_volume_eur: 1e7,
        days_to_trade: 0.0005,
        illiquid: false,
      },
    ],
    breaches: ['Emisor cik:0001067983 (BRK-A, BRK-B) pesa 100.0%'],
  },
  stress: {
    scenarios: [
      {
        id: 'market_correlated',
        label: 'Mercado -20% con correlaciones en 1',
        change: -0.2,
        change_eur: -200,
        exceeds_tolerance: true,
      },
    ],
    notes: ['El 20% es un umbral de revisión.'],
  },
  economic_currency_note: 'Aproximación.',
};
const proposal: PolicyProposal = {
  as_of: '2026-10-31',
  policy_version: 'portfolio-policy-v1',
  policy_revision: null,
  n_positions: 20,
  contribution_eur: 700,
  euros_per_dollar: 0.9,
  excluded: [{ symbol: 'TINY', reason: 'illiquid' }],
  outside_target: [],
  alternatives: [
    {
      label: 'Con los límites de la política',
      weights: [{ symbol: 'AAA', weight: 0.1 }],
      cash: 0.05,
      issuers: [],
      sectors: [],
      breaches: [],
      orders: [
        {
          symbol: 'AAA',
          shares: 3,
          amount_eur: 600,
          commission_eur: 1,
          fx_cost_eur: 3.59,
          gap_eur: 700,
        },
      ],
      residual_cash_eur: 95.41,
      costs_eur: 4.59,
      unfunded: ['BBB'],
    },
  ],
};

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => {
  screen?.unmount();
  vi.clearAllMocks();
});

describe('Riesgo y política (#248)', () => {
  it('agrupa las clases de un emisor, avisa del límite y propone órdenes con costes', async () => {
    api.getPortfolioPolicy.mockResolvedValue(policy);
    api.getRiskPanel.mockResolvedValue(panel);
    api.getPolicyProposal.mockResolvedValue(proposal);
    screen = renderScreen(<RiskPage />);
    await screen.findText('BRK-A, BRK-B');
    await screen.findText('Órdenes para tu aportación');
    expect(screen.text()).toContain('Supera tu tolerancia');
    expect(screen.text()).toContain('TINY (volumen diario por debajo del mínimo)');
    expect(screen.text()).toContain('Quedan para próximas aportaciones: BBB.');
    const issuer = screen.container.querySelector<HTMLInputElement>('[name=max_issuer_weight]');
    expect(issuer?.value).toBe('10');
    expect(api.getPolicyProposal).toHaveBeenCalledWith(700, 20, expect.anything());
  });

  it('sin cambio EUR/USD remite a Perfil y benchmark', async () => {
    api.getPortfolioPolicy.mockResolvedValue(policy);
    api.getRiskPanel.mockResolvedValue({ ...panel, positions: 0 });
    api.getPolicyProposal.mockRejectedValue(
      new ApiError(409, 'benchmark_prices_missing', 'Falta el cambio USDEUR=X en caché.'),
    );
    screen = renderScreen(<RiskPage />);
    await screen.findText('Falta el cambio USDEUR=X en caché.');
    expect(screen.text()).toContain('Ir a Perfil y benchmark');
    expect(screen.text()).toContain('Sin posiciones valoradas.');
  });
});
