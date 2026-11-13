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
    expect(summary.textContent).toContain(
      'Aún sin pruebas de que gane al mercado · Datos al día: 21 oct 2026',
    );
    expect(shown('Estado de la evidencia')).toBe(false);
    expect(shown('Estado de los datos')).toBe(false);
    expect(screen.text()).toContain('Aún no está demostrado que GABI gane al mercado');
    expect(screen.text()).toContain('Con informes oficiales (SEC)');
  });

  it('con datos degradados el aviso completo sigue a la vista', () => {
    screen = renderScreen(
      <Evidence
        model={model}
        data={{ ...data, status: 'stale', warnings: ['prices_stale'], needs_attention: true }}
      />,
    );
    expect(shown('Estado de los datos')).toBe(true);
    expect(screen.text()).toContain('Datos antiguos: conviene actualizarlos');
    // Compact: the warning in words in view; sources and counts folded behind «Ver detalle».
    expect(screen.text()).toContain('Hay precios con más de una semana');
    const detail = screen.container.querySelector<HTMLDetailsElement>(
      'section[aria-label="Estado de los datos"] details',
    )!;
    expect(detail.open).toBe(false);
    expect(detail.textContent).toContain('Con informes oficiales (SEC)');
    expect(screen.container.querySelector('summary')!.textContent).not.toContain('Datos al día');
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
