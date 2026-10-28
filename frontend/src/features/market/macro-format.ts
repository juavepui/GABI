import { useQuery } from '@tanstack/react-query';
import { getMacro } from '@/shared/api/client';
import type { MacroPoint } from '@/shared/api/generated/types.gen';
import { formatCompactMoney, formatNumber } from '@/shared/lib/format';

/** The cached FRED series; reading them never downloads. */
export function useMacro() {
  return useQuery({ queryKey: ['market', 'macro'], queryFn: ({ signal }) => getMacro(signal) });
}

/** A level or a change in the unit the API publishes; dollars read as «billones US$». */
export function amount(value: number | null, unit: string, signed = false): string {
  if (unit === 'USD') {
    const text = formatCompactMoney(value);
    return signed && value != null && value > 0 ? '+' + text : text;
  }
  return formatNumber(value, { digits: 2, signed }) + ' ' + unit;
}

const FREQUENCY: Record<MacroPoint['frequency'], string> = {
  daily: 'Diaria',
  weekly: 'Semanal',
  monthly: 'Mensual',
};

const AGGREGATION: Record<MacroPoint['aggregation'], string> = {
  end_of_period: 'último valor publicado',
  average: 'media del mes',
  year_over_year: 'variación frente al mismo mes del año anterior',
  wednesday_level: 'saldo de cada miércoles',
  three_month_average: 'media de 3 meses',
};

/** «Diaria · último valor publicado», as the backend declares each series. */
export function cadence(item: MacroPoint): string {
  return `${FREQUENCY[item.frequency]} · ${AGGREGATION[item.aggregation]}`;
}

/** ▲ / ▼ / = for the change against three months earlier. */
export function trend(change: number | null | undefined): string {
  if (change == null) return '';
  return change > 0 ? '▲' : change < 0 ? '▼' : '=';
}
