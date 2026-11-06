import { formatNumber } from '@/shared/lib/format';

/** The fields of a ranking/SEC event that the plain description needs. */
export type EventFacts = {
  event_type: string;
  previous_value?: unknown;
  new_value?: unknown;
  cause: string;
};

const asNumber = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

const points = (value: number) => formatNumber(value, { digits: 1 });

/** «basket» is how many companies the saved basket holds (its Top-N), when known. */
function topLabel(basket: number | null | undefined): string {
  return basket ? `las ${basket} primeras` : 'las primeras de la cesta';
}

/** The backend's `cause` is written for diagnostics («El rank cambió +80 posiciones (umbral:
 *  5)»); here each event says, in plain words, where the company was and where it is now.
 *  The values are the backend's; only the wording changes. Unknown types keep `cause`. */
export function eventText(event: EventFacts, basket?: number | null): string {
  const before = asNumber(event.previous_value);
  const now = asNumber(event.new_value);
  switch (event.event_type) {
    case 'rank_change': {
      if (before == null || now == null) break;
      const moved = Math.abs(now - before);
      // Puesto 1 is the best: a bigger number means it has fallen.
      const verb = now > before ? 'Baja' : 'Sube';
      return `${verb} del puesto ${before} al ${now} del ranking (${moved} puestos).`;
    }
    case 'top_n_entry':
      return now == null
        ? `Entra entre ${topLabel(basket)} del ranking.`
        : `Entra entre ${topLabel(basket)} del ranking: ahora está en el puesto ${now}.`;
    case 'top_n_exit':
      return before == null
        ? `Sale de ${topLabel(basket)} del ranking.`
        : `Sale de ${topLabel(basket)} del ranking: estaba en el puesto ${before}. Su puesto de hoy está en su ficha.`;
    case 'score_change': {
      if (before == null || now == null) break;
      const verb = now > before ? 'Sube' : 'Baja';
      return `${verb} su puntuación GABI de ${points(before)} a ${points(now)} sobre 100 (${formatNumber(now - before, { digits: 1, signed: true })} puntos).`;
    }
    case 'confidence_drop':
      if (before == null || now == null) break;
      return `Tiene menos datos para puntuarla: antes un ${points(before)} % de lo necesario, ahora un ${points(now)} %.`;
    case 'sector_change':
      if (typeof event.previous_value !== 'string' || typeof event.new_value !== 'string') break;
      return `Ahora figura en otro sector: antes «${event.previous_value}», ahora «${event.new_value}».`;
    case 'eligibility_change':
      return before == null
        ? 'Ya no se puede puntuar: le faltan datos.'
        : `Ya no se puede puntuar: le faltan datos (antes tenía ${points(before)} puntos sobre 100).`;
  }
  return event.cause;
}
