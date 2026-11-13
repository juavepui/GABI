import { describe, expect, it } from 'vitest';
import { eventText } from '@/features/market/event-text';

const event = (event_type: string, previous_value: unknown, new_value: unknown) => ({
  event_type,
  previous_value,
  new_value,
  cause: 'texto del backend',
});

describe('avisos de Eventos en palabras', () => {
  it('dice de qué puesto a qué puesto se mueve y en qué dirección', () => {
    expect(eventText(event('rank_change', 12, 92))).toBe(
      'Baja del puesto 12 al 92 del ranking (80 puestos).',
    );
    expect(eventText(event('rank_change', 30, 24))).toBe(
      'Sube del puesto 30 al 24 del ranking (6 puestos).',
    );
  });

  it('dice el tamaño de la cesta y el puesto al entrar o salir', () => {
    expect(eventText(event('top_n_entry', null, 7), 20)).toBe(
      'Entra entre las 20 primeras del ranking: ahora está en el puesto 7.',
    );
    expect(eventText(event('top_n_exit', 15, null), 20)).toBe(
      'Sale de las 20 primeras del ranking: estaba en el puesto 15. Su puesto de hoy está en su ficha.',
    );
    expect(eventText(event('top_n_exit', null, null))).toBe(
      'Sale de las primeras de la cesta del ranking.',
    );
  });

  it('da la puntuación de antes y la de ahora sobre 100', () => {
    expect(eventText(event('score_change', 72.3, 60.7))).toBe(
      'Baja su puntuación GABI de 72,3 a 60,7 sobre 100 (-11,6 puntos).',
    );
  });

  it('explica la falta de datos, el sector y lo que no reconoce', () => {
    expect(eventText(event('confidence_drop', 90, 65))).toBe(
      'Tiene menos datos para puntuarla: antes un 90 % de lo necesario, ahora un 65 %.',
    );
    expect(eventText(event('sector_change', 'Energy', 'Utilities'))).toBe(
      'Ahora figura en otro sector: antes «Energy», ahora «Utilities».',
    );
    expect(eventText(event('filing_revenue_drop', null, null))).toBe('texto del backend');
    expect(eventText(event('rank_change', null, 5))).toBe('texto del backend');
  });
});
