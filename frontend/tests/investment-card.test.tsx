import { afterEach, describe, expect, it, vi } from 'vitest';
import type { InvestmentCard } from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({
  getCompanyCards: vi.fn(),
  createCard: vi.fn(),
  saveCard: vi.fn(),
  moveCard: vi.fn(),
}));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { InvestmentCardSection } = await import('../src/features/market/investment-card');

const base: InvestmentCard = {
  id: 1,
  symbol: 'ACME',
  version: 1,
  state: 'incompleta',
  created_at: '2026-11-01',
  updated_at: '2026-11-01',
  published_at: null,
  discarded_at: null,
  discard_reason: null,
  content: { thesis: ['Recompra con caja libre creciente.'] },
  snapshot: null,
  snapshot_sha256: null,
  missing: ['la expectativa discrepante', 'la fecha de revisión'],
  scenario_returns: { bear: null, base: null, bull: null },
  version_rules: 'investment-card-v1',
  not_a_probability: 'Ninguna es una probabilidad de beneficio.',
};

afterEach(() => vi.clearAllMocks());

describe('ficha de inversión', () => {
  it('invita a empezarla cuando no hay ninguna', async () => {
    api.getCompanyCards.mockResolvedValue({ items: [] });
    const screen = renderScreen(<InvestmentCardSection symbol="ACME" />);
    await screen.findText('Empezar la ficha');
    expect(screen.text()).toContain('Descartarla también es una conclusión válida');
    screen.unmount();
  });

  it('muestra lo que falta para publicar un borrador y no deja publicarlo', async () => {
    api.getCompanyCards.mockResolvedValue({ items: [base] });
    const screen = renderScreen(<InvestmentCardSection symbol="ACME" />);
    await screen.findText('Para publicar falta la expectativa discrepante; la fecha de revisión.');
    const publish = [...screen.container.querySelectorAll('button')].find(
      (button) => button.textContent === 'Publicar',
    );
    expect(publish?.hasAttribute('disabled')).toBe(true);
    expect(screen.text()).toContain('v1 · Incompleta');
    screen.unmount();
  });

  it('separa cobertura, evidencia y confianza en una versión publicada', async () => {
    const published: InvestmentCard = {
      ...base,
      state: 'publicada',
      published_at: '2026-11-01',
      missing: [],
      content: {
        thesis: ['Recompra con caja libre creciente.'],
        discrepancy: 'El precio implica declive del FCF.',
        scenarios: {
          bear: { price: 80, assumptions: 'FCF −5 %' },
          base: { price: 110, assumptions: 'estable' },
          bull: { price: 140, assumptions: 'FCF +5 %' },
        },
        catalysts: [{ description: 'Resultados', horizon: '2027-02-15' }],
        risks: ['Pérdida del contrato'],
        invalidation: [],
        confidence: 'media',
        review_due: '2027-05-01',
      },
      snapshot: {
        price: { value: 100, date: '2026-10-30' },
        evidence: { data_coverage: 0.8, statistical_evidence: 'retrospectiva' },
        absent: ['métrica: Deuda'],
        decision: {
          position_eur: 2000,
          costs: { buy_eur: 13, round_trip_eur: 26, round_trip_share: 0.013 },
          concentration: {
            issuer_weight_after: 0.1,
            issuer_cap: 0.1,
            issuer_exceeds: false,
            sector: 'Industrials',
            sector_weight_after: 0.325,
            sector_cap: 0.3,
            sector_exceeds: true,
          },
          passive: {
            horizon_days: 181,
            base_annualised_net: 0.18,
            index_annualised_past: 0.12,
            margin_over_index: 0.06,
            costs_included: true,
            note: 'Ninguna cifra es una previsión.',
          },
        },
      },
      snapshot_sha256: 'a'.repeat(64),
      scenario_returns: { bear: -0.2, base: 0.1, bull: 0.4 },
    };
    api.getCompanyCards.mockResolvedValue({ items: [published] });
    const screen = renderScreen(<InvestmentCardSection symbol="ACME" />);
    await screen.findText('Cobertura del dato');
    const text = screen.text();
    expect(text).toContain('Evidencia estadística del modelo');
    expect(text).toContain('Tu confianza subjetiva');
    expect(text).toContain('Ninguna es una probabilidad de beneficio.');
    expect(text).toContain('Sin dato al publicar: métrica: Deuda');
    expect(text).toContain('Abrir una versión nueva');
    expect(text).toContain('26 € ida y vuelta');
    expect(text).toContain('Industrials 32,5 % (límite 30 %) · lo supera');
    expect(text).toContain('S&P 500 en € 12 % anual pasado');
    expect(text).toContain('Ninguna cifra es una previsión.');
    expect(text).not.toContain('durante  periodos');
    screen.unmount();
  });
});
