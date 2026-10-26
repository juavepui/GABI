import { afterEach, describe, expect, it } from 'vitest';
import type { DecisionFreshness } from '../src/shared/api/generated/types.gen';
import { PlanFreshness } from '../src/features/portfolio/decisions-page';
import { renderScreen } from './render';

const base: DecisionFreshness = {
  age_days: 35,
  today: '2026-10-21',
  positions: 9,
  threshold_points: 5,
  material: false,
  changes: [],
};
let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

describe('aviso de plan desfasado (#191)', () => {
  it('un plan respaldado por el ranking actual solo muestra su antigüedad', () => {
    screen = renderScreen(<PlanFreshness data={base} />);
    expect(screen.text()).toContain('Guardado hace 35 días');
    expect(screen.container.querySelector('[role="alert"]')).toBeNull();
  });

  it('avisa del desfase con cada posición que ha cambiado', () => {
    screen = renderScreen(
      <PlanFreshness
        data={{
          ...base,
          material: true,
          changes: [
            {
              symbol: 'INCY',
              saved_score: 80.61,
              current_score: 71.1,
              label: 'Su score ha cambiado 5 puntos o más',
            },
            {
              symbol: 'GONE',
              saved_score: 70,
              current_score: null,
              label: 'Ya no tiene score en el ranking actual',
            },
          ],
        }}
      />,
    );
    const alert = screen.container.querySelector('[role="alert"]')!;
    expect(alert.textContent).toContain(
      'Plan desfasado: guardado hace 35 días, el ranking ha cambiado en 2 de sus 9 posiciones.',
    );
    expect(alert.textContent).toContain(
      'INCY: Su score ha cambiado 5 puntos o más (score 80,61 → 71,1)',
    );
    expect(alert.textContent).toContain('GONE: Ya no tiene score en el ranking actual');
    expect(alert.textContent).toContain('sin score');
  });
});
