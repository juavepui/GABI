import { afterEach, describe, expect, it } from 'vitest';
import type { DataResponse, ModelResponse } from '../src/shared/api/generated/types.gen';
import { Evidence } from '../src/features/market/evidence';
import { renderScreen } from './render';

const model: ModelResponse = {
  mode: 'INVESTOR',
  model_id: 'GABI-MF-v1',
  status: 'LIVE_FORWARD',
  weights: {},
  weights_unit: 'fraction',
  matches_frozen: true,
  live_forward_source: 'blind_validation',
  blind_validation_id: 1,
  independent_advantage_demonstrated: false,
  evidence_note: 'Seguimiento sin conclusión.',
} as ModelResponse;

const data: DataResponse = {
  status: 'ready',
  universe_count: 503,
  prices_available: 503,
  fundamentals_available: 503,
  sec_available: 502,
  scored_count: 500,
  latest_price_date: '2026-10-21',
  warnings: ['incomplete_coverage'],
  last_session: '2026-10-21',
  prices_current: true,
  needs_attention: false,
};

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

/** The region is in view unless it sits inside a closed <details>. */
function shown(name: string) {
  const region = screen!.container.querySelector(`section[aria-label="${name}"]`);
  if (!region) return false;
  const fold = region.closest('details');
  return fold === null || fold.open;
}

describe('avisos de evidencia y datos (#187)', () => {
  it('la situación habitual se pliega en un chip con el mismo detalle', () => {
    screen = renderScreen(<Evidence model={model} data={data} />);
    const summary = screen.container.querySelector('summary')!;
    expect(summary.textContent).toContain('Evidencia: no demostrada · Datos: al día 21 oct 2026');
    expect(shown('Estado de la evidencia')).toBe(false);
    expect(shown('Estado de los datos')).toBe(false);
    expect(screen.text()).toContain('Ventaja frente a SPY no demostrada');
    expect(screen.text()).toContain('Con datos SEC');
  });

  it('con datos degradados el aviso completo sigue a la vista', () => {
    screen = renderScreen(
      <Evidence
        model={model}
        data={{ ...data, status: 'stale', warnings: ['prices_stale'], needs_attention: true }}
      />,
    );
    expect(shown('Estado de los datos')).toBe(true);
    expect(screen.text()).toContain('Datos obsoletos');
    expect(screen.container.querySelector('summary')!.textContent).not.toContain('Datos:');
    expect(shown('Estado de la evidencia')).toBe(false);
  });

  it('Research con pesos no congelados muestra la evidencia completa', () => {
    screen = renderScreen(
      <Evidence model={{ ...model, mode: 'RESEARCH', matches_frozen: false }} data={data} />,
    );
    expect(shown('Estado de la evidencia')).toBe(true);
    expect(shown('Estado de los datos')).toBe(false);
  });
});
