import { afterEach, describe, expect, it } from 'vitest';
import { ChartFrame } from '../src/shared/ui/charts/chart-frame';
import { RangeDot } from '../src/shared/ui/charts/range-dot';
import { renderScreen } from './render';

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());
const ratio = (value: number) => value.toFixed(1).replace('.', ',');

describe('piezas comunes de gráficas (#323)', () => {
  it('ChartFrame pone la pregunta y la conclusión antes de la gráfica y ofrece la tabla', () => {
    screen = renderScreen(
      <ChartFrame
        title="¿Está cara o barata?"
        conclusion="PER de 14,0: más barata de lo habitual en ella."
        table={<table aria-label="Datos" />}
        note="Nota de fuente"
      >
        <div>gráfica</div>
      </ChartFrame>,
    );
    const text = screen.text();
    expect(text.indexOf('¿Está cara o barata?')).toBeLessThan(text.indexOf('gráfica'));
    expect(text.indexOf('más barata de lo habitual')).toBeLessThan(text.indexOf('gráfica'));
    expect(text).toContain('Ver como tabla');
    expect(text).toContain('Nota de fuente');
  });

  it('RangeDot se lee en palabras y muestra extremos, hoy y referencias', () => {
    screen = renderScreen(
      <RangeDot
        min={12}
        max={95}
        value={14}
        marks={[
          { value: 18, label: 'Su mediana' },
          { value: 20, label: 'Sector' },
        ]}
        format={ratio}
        description="PER de 14,0: más barata de lo habitual en ella (mediana de 18,0)."
      />,
    );
    const image = screen.container.querySelector('[role="img"]');
    expect(image?.getAttribute('aria-label')).toBe(
      'PER de 14,0: más barata de lo habitual en ella (mediana de 18,0).',
    );
    const text = screen.text();
    expect(text).toContain('más barata · 12,0');
    expect(text).toContain('95,0 · más cara');
    expect(text).toContain('Hoy 14,0');
    expect(text).toContain('Su mediana 18,0');
    expect(text).toContain('Sector 20,0');
  });

  it('RangeDot coloca el punto aunque hoy quede fuera del rango de sus años', () => {
    screen = renderScreen(
      <RangeDot
        min={10}
        max={20}
        value={30}
        format={ratio}
        description="Hoy más cara que nunca."
      />,
    );
    const dots = screen.container.querySelectorAll('[style*="left"]');
    const lefts = Array.from(dots).map((node) => (node as HTMLElement).style.left);
    expect(lefts).toContain('100%');
    // «Hoy» sits over the dot and, at the right edge, grows inwards.
    expect(screen.text()).toContain('Hoy 30,0');
  });
});
