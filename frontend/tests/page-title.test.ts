import { describe, expect, it } from 'vitest';
import { pageTitle, REDIRECTS, sectionOf, sections } from '../src/app/navigation';

describe('título de la pestaña por ruta (#177)', () => {
  it('va del apartado más específico al general', () => {
    expect(pageTitle('/')).toBe('Resumen · GABI');
    expect(pageTitle('/macro')).toBe('Panel macro · GABI');
    expect(pageTitle('/cartera/seguimiento')).toBe('Seguimiento · GABI');
    expect(pageTitle('/eventos')).toBe('Eventos · GABI');
    expect(pageTitle('/ayuda')).toBe('Ayuda · GABI');
    expect(pageTitle('/cartera', '?plan=experimental')).toBe('Plan experimental · GABI');
    expect(pageTitle('/descubrir')).toBe('Ranking · GABI');
    expect(pageTitle('/cartera')).toBe('Cartera objetivo · GABI');
    expect(pageTitle('/administracion/calidad')).toBe('Calidad de los datos · GABI');
    expect(pageTitle('/empresas/BRK.B')).toBe('BRK.B · Ficha · GABI');
  });

  it('nombra las empresas comparadas', () => {
    expect(pageTitle('/descubrir/comparar', '?symbols=ALL&symbols=TRV')).toBe(
      'Comparar ALL, TRV · GABI',
    );
    expect(pageTitle('/descubrir/comparar')).toBe('Comparar empresas · GABI');
  });

  it('una ruta desconocida se titula solo «GABI»', () => {
    expect(pageTitle('/no-existe')).toBe('GABI');
  });
});

describe('secciones por tarea (#188)', () => {
  it('cada ruta pertenece a su sección, incluida la ficha sin entrada propia', () => {
    const label = (path: string) => sectionOf(path)?.label;
    expect(label('/')).toBe('Hoy');
    expect(label('/macro')).toBe('Hoy');
    expect(label('/descubrir/comparar')).toBe('Descubrir');
    expect(label('/empresas/APA')).toBe('Descubrir');
    expect(label('/cartera/seguimiento')).toBe('Cartera');
    expect(label('/eventos')).toBe('Hoy');
    expect(label('/investigacion/factores')).toBe('Investigación');
    expect(label('/administracion/calidad')).toBe('Administración');
    expect(label('/ayuda')).toBeUndefined();
    expect(label('/no-existe')).toBeUndefined();
  });

  it('las rutas antiguas llevan a una página que existe en el mapa nuevo', () => {
    for (const { from, to } of REDIRECTS) {
      const target = to({ symbol: 'APA' });
      expect(target, from).not.toMatch(/^\/mercado|aprender/);
      expect(sectionOf(target.split('?')[0]) || target === '/ayuda', from).toBeTruthy();
    }
  });
});

describe('navegación en castellano (#193)', () => {
  it('ninguna sección ni apartado del menú se nombra en inglés', () => {
    const labels = sections.flatMap((section) => [
      section.label,
      ...section.pages.map((page) => page.label),
    ]);
    expect(labels.filter((label) => /\b(Lab|Monitor|Signal|Screener)\b/.test(label))).toEqual([]);
  });
});
