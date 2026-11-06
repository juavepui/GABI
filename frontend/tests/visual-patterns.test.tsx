import { afterEach, describe, expect, it } from 'vitest';
import { Activity } from 'lucide-react';
import { Direction, StatusTag } from '../src/shared/ui/status';
import { SummaryCard } from '../src/shared/ui/summary-card';
import { VerdictBanner } from '../src/shared/ui/verdict-banner';
import type { Tone } from '../src/shared/ui/tone';
import { renderScreen } from './render';

let screen: ReturnType<typeof renderScreen> | undefined;
afterEach(() => screen?.unmount());

const COLOURS = /text-(success|danger|warning)|bg-(success|danger|warning)(?!-soft)/;

describe('Patrones visuales (#320)', () => {
  it('SummaryCard: cabecera con título como encabezado, «Ver más» y el contenido debajo', () => {
    screen = renderScreen(
      <SummaryCard
        title="Cómo está el mercado"
        icon={Activity}
        more={{ to: '/macro' }}
        verdict={<p>Veredicto</p>}
      >
        <p>Filas</p>
      </SummaryCard>,
    );
    const section = screen.container.querySelector('section[aria-label="Cómo está el mercado"]');
    expect(section?.querySelector('h2')?.textContent).toBe('Cómo está el mercado');
    const link = section?.querySelector('a');
    expect(link?.getAttribute('href')).toBe('/macro');
    expect(link?.textContent).toContain('Ver más');
    expect(screen.text().indexOf('Veredicto')).toBeLessThan(screen.text().indexOf('Filas'));
  });

  it.each<[Tone, string]>([
    ['good', 'Favorable'],
    ['caution', 'Con presión'],
    ['bad', 'En corrección'],
    ['neutral', 'Sin puntuación'],
  ])(
    'VerdictBanner %s: el veredicto se lee en palabras y lleva icono, no solo color',
    (tone, verdict) => {
      screen = renderScreen(
        <VerdictBanner
          tone={tone}
          verdict={verdict}
          explanation="Una línea que lo explica."
          value="67 de 100"
          valueLabel="Nota"
        />,
      );
      const banner = screen.container.querySelector(`[data-tone="${tone}"]`);
      expect(banner?.textContent).toContain(verdict);
      expect(banner?.querySelector('svg')).not.toBeNull();
      expect(screen.text()).toContain('Una línea que lo explica.');
      expect(screen.text()).toContain('67 de 100');
    },
  );

  it.each<[Tone, string]>([
    ['good', 'Pasa'],
    ['caution', 'Precaución'],
    ['bad', 'Falla'],
    ['neutral', 'Sin dato'],
  ])('StatusTag %s: borde, icono y palabra', (tone, label) => {
    screen = renderScreen(<StatusTag tone={tone} label={label} />);
    const tag = screen.container.querySelector(`[data-tone="${tone}"]`);
    expect(tag?.textContent).toBe(label);
    expect(tag?.className).toContain('border');
    expect(tag?.querySelector('svg')).not.toBeNull();
  });

  it.each([
    [3.2, 'up', '↑', 'sube'],
    [-1, 'down', '↓', 'baja'],
    [0, 'flat', '→', 'igual'],
  ])(
    'Direction %s: flecha y palabra en color neutro, separadas del nivel',
    (value, way, arrow, word) => {
      screen = renderScreen(<Direction value={value}>2 puntos</Direction>);
      const direction = screen.container.querySelector(`[data-direction="${way}"]`);
      expect(direction?.textContent).toBe(`${arrow} ${word} 2 puntos`);
      expect(direction?.className).toContain('text-muted-foreground');
      expect(direction?.outerHTML).not.toMatch(COLOURS);
      // The arrow is decoration; the word carries the direction for screen readers.
      expect(direction?.querySelector('[aria-hidden="true"]')?.textContent?.trim()).toBe(arrow);
    },
  );
});
