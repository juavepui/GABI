import { afterEach, describe, expect, it, vi } from 'vitest';
import type { IdeaList } from '../src/shared/api/generated/types.gen';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({
  getIdeas: vi.fn(),
  getIdea: vi.fn(),
  addIdeaEvent: vi.fn(),
  addIdeaNote: vi.fn(),
  deleteIdeaNote: vi.fn(),
}));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  ...api,
}));
const { IdeasPage } = await import('../src/features/portfolio/ideas-page');

const listing: IdeaList = {
  version: 'ideas-v1',
  as_of: '2026-11-01',
  benchmark: 'S&P 500 en EUR',
  summary: {
    ideas: 2,
    open: 1,
    closed: 1,
    retired: 0,
    evaluated: 1,
    beat_index: 0,
    median_excess: -0.08,
    mean_excess: -0.08,
    thesis_hits: { acertada: 0, parcial: 0, fallida: 1 },
    note: 'Cuentan todas.',
  },
  items: [
    {
      idea_id: 2,
      symbol: 'LOSS',
      card_id: 2,
      review_due: '2027-01-01',
      chain_ok: true,
      state: {
        status: 'cerrada',
        published_on: '2026-03-02',
        ended_on: '2026-09-01',
        outcome: { outcome: 'fallida', cause: 'margen', executed: true },
        reviews: 0,
        corrections: 0,
      },
      evaluation: {
        status: 'ok',
        return_net: -0.05,
        index_return: 0.03,
        excess: -0.08,
        max_drawdown: -0.12,
        days: 183,
      },
    },
    {
      idea_id: 1,
      symbol: 'NEW',
      card_id: 1,
      review_due: null,
      chain_ok: false,
      state: {
        status: 'abierta',
        published_on: '2026-10-30',
        ended_on: null,
        outcome: null,
        reviews: 0,
        corrections: 0,
      },
      evaluation: { status: 'insufficient_prices', missing: ['NEW'] },
    },
  ],
};

afterEach(() => vi.clearAllMocks());

describe('historial de ideas', () => {
  it('muestra todas las ideas, también las perdedoras, frente al S&P 500', async () => {
    api.getIdeas.mockResolvedValue(listing);
    const screen = renderScreen(<IdeasPage />);
    await screen.findText('2 ideas (1 abiertas, 1 cerradas, 0 retiradas)');
    const text = screen.text();
    expect(text).toContain('0 de 1 evaluadas superan al índice');
    expect(text).toContain('tesis acertadas 0, parciales 0, fallidas 1');
    expect(text).toContain('-5 % neto · S&P 500 +3 % · diferencia -8 %');
    expect(text).toContain('Sin precios suficientes en caché (NEW)');
    expect(text).toContain('Historial alterado');
    expect(text).toContain('nada se reescribe ni se borra');
    screen.unmount();
  });
});
