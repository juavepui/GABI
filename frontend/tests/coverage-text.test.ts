import { describe, expect, it } from 'vitest';
import { plainWarning } from '@/shared/lib/coverage-text';

describe('avisos de cobertura en lenguaje llano', () => {
  it('traduce el aviso de un apartado con datos incompletos', () => {
    expect(
      plainWarning(
        '**Quality**: solo 0% del universo tiene TODAS las métricas de este bloque (umbral configurado: 70%).',
      ),
    ).toBe(
      '**Calidad**: solo el 0 % de las empresas tiene todos los datos de este apartado (mínimo pedido: 70 %).',
    );
  });

  it('traduce los avisos de identidad y de sector', () => {
    expect(
      plainWarning('Identidad histórica sin acreditar en 33% del universo; excluida del score.'),
    ).toContain('En el 33 % de las empresas no se ha podido confirmar su historia');
    expect(plainWarning('Sector aproximado o ausente en 67% del universo.')).toContain(
      'En el 67 % de las empresas el sector es aproximado o falta',
    );
  });

  it('deja tal cual un aviso que no conoce', () => {
    expect(plainWarning('Aviso nuevo del backend.')).toBe('Aviso nuevo del backend.');
  });
});
