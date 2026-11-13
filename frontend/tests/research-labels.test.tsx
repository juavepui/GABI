import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PublishedFactors } from '../src/shared/api/generated/types.gen';
import { Hash, HashText } from '../src/shared/ui/hash';
import { renderScreen } from './render';

const api = vi.hoisted(() => ({ getPublishedFactors: vi.fn() }));
vi.mock('@/shared/api/client', async (actual) => ({
  ...(await actual<typeof import('../src/shared/api/client')>()),
  getPublishedFactors: api.getPublishedFactors,
}));
const { PublishedFactorMap } = await import('../src/features/research/published-factor-map');

const SHA = 'c6d9' + '0123456789abcdef'.repeat(3) + '012345678901';
let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

describe('hashes legibles (#176)', () => {
  it('muestra 8 caracteres y deja el valor completo en la ayuda y en el botón de copiar', () => {
    screen = renderScreen(<Hash value={SHA} />);
    expect(screen.text()).toBe(SHA.slice(0, 8) + '…');
    expect(screen.container.querySelector('code')?.title).toBe(SHA);
    expect(screen.container.querySelector('button')?.getAttribute('aria-label')).toContain(SHA);
  });

  it('acorta los hashes dentro de un texto libre', () => {
    screen = renderScreen(
      <HashText text={`Ampliación A3 de ['${SHA}', '${SHA}']; sha256 ${SHA}`} copy={false} />,
    );
    expect(screen.text()).toBe(`Ampliación A3 de ['c6d90123…', 'c6d90123…']; sha256 c6d90123…`);
    expect(screen.container.querySelector('button')).toBeNull();
  });
});

describe('Factor Lab (#176)', () => {
  it('muestra la clasificación por su nombre y explica cada una junto a la tabla', async () => {
    api.getPublishedFactors.mockResolvedValue({
      holm_significant_count: 0,
      n_dates: 57,
      factor_zoo_sha256: SHA,
      sic_sha256: SHA,
      minimum_pairs: 30,
      minimum_summary_periods: 30,
      n_eligible: 10,
      n_classified: 9,
      classified_fraction: 0.9,
      coverage: [],
      factors: [
        {
          metric: 'pb',
          ic_mean: 0.01,
          icir: 0.1,
          p_holm: 1,
          classification: 'indicio',
          classification_label: 'Indicio no significativo',
          classification_meaning: 'IC medio > 0, pero no supera la corrección Holm.',
          n_periods: 57,
          q_spread: 0.01,
          sic_divisions: [],
        },
      ],
      classifications: [
        { code: 'sin_evidencia', label: 'Sin evidencia', meaning: 'IC medio ≤ 0.' },
        {
          code: 'indicio',
          label: 'Indicio no significativo',
          meaning: 'IC medio > 0, pero no supera la corrección Holm.',
        },
      ],
    } as unknown as PublishedFactors);
    screen = renderScreen(<PublishedFactorMap />);
    await screen.findText('Indicio no significativo');
    const table = screen.container.querySelector('table')!;
    expect(table.textContent).toContain('Indicio no significativo');
    expect(table.textContent).not.toMatch(/\w_\w/);
    const legend = screen.container.querySelector(
      'dl[aria-label="Qué significa cada clasificación"]',
    );
    expect(legend?.textContent).toContain('Sin evidenciaIC medio ≤ 0.');
    expect(screen.text()).not.toContain(SHA);
  });
});
