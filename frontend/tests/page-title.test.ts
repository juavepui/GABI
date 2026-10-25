import { describe, expect, it } from 'vitest';
import { pageTitle } from '../src/app/navigation';

describe('título de la pestaña por ruta (#177)', () => {
  it('va del apartado más específico al general', () => {
    expect(pageTitle('/')).toBe('Inicio · GABI');
    expect(pageTitle('/mercado')).toBe('Ranking · GABI');
    expect(pageTitle('/cartera')).toBe('Cartera objetivo · GABI');
    expect(pageTitle('/administracion/calidad')).toBe('Calidad de los datos · GABI');
    expect(pageTitle('/mercado/empresas/BRK.B')).toBe('BRK.B · Ficha · GABI');
  });

  it('nombra las empresas comparadas', () => {
    expect(pageTitle('/mercado/comparar', '?symbols=ALL&symbols=TRV')).toBe(
      'Comparar ALL, TRV · GABI',
    );
    expect(pageTitle('/mercado/comparar')).toBe('Comparar empresas · GABI');
  });

  it('una ruta desconocida se titula solo «GABI»', () => {
    expect(pageTitle('/no-existe')).toBe('GABI');
  });
});
