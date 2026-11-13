import { act } from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { Activity } from 'lucide-react';
import { Direction, StatusTag } from '../src/shared/ui/status';
import { SummaryCard } from '../src/shared/ui/summary-card';
import { SuspectMark, SuspectNote } from '../src/shared/ui/suspect-mark';
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

describe('Patrones visuales, segunda parte (#320)', () => {
  it('activeFilters: cada filtro en palabras y se quita solo él', async () => {
    const { activeFilters } = await import('../src/features/market/active-filters');
    const params = new URLSearchParams(
      'search=app&sectors=Energy&sectors=Financials&exclude_sectors=Utilities&min_market_cap=1000000000' +
        '&earnings=only&earnings_days=7&golden_cross_only=true&hide_no_data=false',
    );
    const filters = activeFilters(params);
    expect(filters.map((filter) => filter.label)).toEqual([
      'Busca «app»',
      'Sector: Energy',
      'Sector: Financials',
      'Sin el sector Utilities',
      expect.stringMatching(/^Capitalización desde /),
      'Presentan resultados en los próximos 7 días',
      'Con cruce dorado reciente',
      'Incluye empresas sin datos',
    ]);
    expect(filters[1].remove).toEqual({ sectors: ['Financials'] });
    expect(activeFilters(new URLSearchParams())).toEqual([]);
  });

  it('ActiveFilterTags: «×» quita ese filtro', async () => {
    const { ActiveFilterTags } = await import('../src/features/market/active-filter-tags');
    const removed: unknown[] = [];
    screen = renderScreen(
      <ActiveFilterTags
        filters={[
          {
            key: 'golden',
            label: 'Con cruce dorado reciente',
            remove: { golden_cross_only: null },
          },
        ]}
        remove={(updates) => removed.push(updates)}
      />,
    );
    const button = screen.container.querySelector<HTMLButtonElement>(
      'button[aria-label="Quitar filtro: Con cruce dorado reciente"]',
    );
    act(() => button?.click());
    expect(removed).toEqual([{ golden_cross_only: null }]);
  });

  it('ScoreBar: ancho de 0 a 100, decorativa y nada sin dato', async () => {
    const { ScoreBar } = await import('../src/shared/ui/score-bar');
    screen = renderScreen(
      <>
        <ScoreBar value={68.7} />
        <ScoreBar value={140} />
        <ScoreBar value={null} />
      </>,
    );
    const bars = [...screen.container.querySelectorAll<HTMLElement>('[data-score-bar]')];
    expect(bars.map((bar) => bar.dataset.scoreBar)).toEqual(['69', '100']);
    expect(bars.every((bar) => bar.getAttribute('aria-hidden') === 'true')).toBe(true);
  });

  it('HowToRead: panel lateral que se abre, se cierra con Escape y solo uno a la vez', async () => {
    const { HowToRead } = await import('../src/shared/ui/how-to-read');
    screen = renderScreen(
      <>
        <HowToRead>Primera explicación.</HowToRead>
        <HowToRead title="Otra">Segunda explicación.</HowToRead>
      </>,
    );
    // Closed, the text is still in the page (search, screen readers) but not drawn.
    expect(screen.text()).toContain('Primera explicación.');
    const [first, second] = [
      ...screen.container.querySelectorAll<HTMLButtonElement>('button[aria-expanded]'),
    ];
    const panels = [...screen.container.querySelectorAll('aside')];
    expect(panels.every((panel) => panel.hidden)).toBe(true);
    act(() => first.click());
    expect(panels[0].hidden).toBe(false);
    expect(first.getAttribute('aria-expanded')).toBe('true');
    act(() => second.click());
    expect(panels.map((panel) => panel.hidden)).toEqual([true, false]);
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(panels[1].hidden).toBe(true);
    expect(document.activeElement).toBe(second);
  });
});

describe('Cifras que parecen un error (#353)', () => {
  it('SuspectMark explica el rango en la unidad del dato y si cuenta para la puntuación', () => {
    screen = renderScreen(
      <>
        <SuspectMark suspect={{ low: -10, high: 1, scored: true }} unit="fraction" label />
        <SuspectMark suspect={{ low: 0, high: 5, scored: false }} unit="fraction" />
        <SuspectMark suspect={undefined} unit="ratio" label />
      </>,
    );
    const tips = [...screen.container.querySelectorAll('[role="tooltip"]')].map(
      (tip) => tip.textContent,
    );
    expect(tips).toHaveLength(2);
    expect(tips[0]).toContain('entre -1000,0 % y 100,0 %');
    expect(tips[0]).toContain('GABI la usa tal cual');
    expect(tips[1]).toContain('No cuenta para la puntuación');
    expect(screen.text()).toContain('Parece un error');
  });

  it('SuspectNote solo aparece si alguna cifra marcada cuenta para la puntuación', () => {
    screen = renderScreen(<SuspectNote suspects={{ roe: { low: -5, high: 5, scored: false } }} />);
    expect(screen.text()).toBe('');
    screen.unmount();
    screen = renderScreen(
      <SuspectNote
        suspects={{
          operating_margin: { low: -10, high: 1, scored: true },
          ev_ebitda: { low: 0, high: 500, scored: true },
        }}
      />,
    );
    expect(screen.text()).toContain('2 cifras que cuentan para la puntuación parecen errores');
    expect(screen.container.querySelector('a')?.getAttribute('href')).toBe('#metricas');
  });
});
