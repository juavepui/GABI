import type { Metric } from '@/shared/api/generated/types.gen';

export type NumberOptions = {
  /** Decimal places; maximum unless `fixed`. */
  digits?: number;
  /** Always show `digits` decimals (1,50 instead of 1,5). */
  fixed?: boolean;
  /** Always show the sign (+1,5). */
  signed?: boolean;
};

/** Every number GABI shows goes through here: Spanish separators and «—» for an absent value. */
export function formatNumber(
  value: number | null | undefined,
  { digits = 2, fixed = false, signed = false }: NumberOptions = {},
): string {
  if (value == null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('es-ES', {
    maximumFractionDigits: digits,
    minimumFractionDigits: fixed ? digits : 0,
    signDisplay: signed ? 'always' : 'auto',
  }).format(value);
}

/** A fraction (0,091) shown as a percentage (9,1 %). */
export function formatPercent(
  fraction: number | null | undefined,
  options: NumberOptions = {},
): string {
  if (fraction == null || Number.isNaN(fraction)) return '—';
  return formatNumber(fraction * 100, { digits: 1, ...options }) + ' %';
}

export function formatMoney(
  value: number | null | undefined,
  { currency = 'USD', digits = 0 }: { currency?: string; digits?: number } = {},
): string {
  if (value == null || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('es-ES', {
    style: 'currency',
    currency,
    maximumFractionDigits: digits,
  }).format(value);
}

const number = (value: number, digits = 2) => formatNumber(value, { digits, fixed: true });
export function metric(value: Metric | undefined, compact = false): string {
  if (value?.value == null) return '—';
  if (value.unit === 'fraction') return number(value.value * 100, 1) + ' %';
  if (value.unit === 'percent') return number(value.value, 1) + ' %';
  if (value.unit === 'count') return number(value.value, 0);
  if (value.unit === 'USD') {
    const formatted = new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency: 'USD',
      notation: compact ? 'compact' : 'standard',
      maximumFractionDigits: 2,
    }).format(value.value);
    // Compact currency labels must wrap in narrow cards; Intl uses no-break spaces.
    return compact ? formatted.replace(/[\u00a0\u202f]/g, ' ') : formatted;
  }
  return number(value.value, 1);
}
export function dateLabel(value: string | null | undefined): string {
  if (!value) return 'Sin fecha';
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? 'Sin fecha'
    : new Intl.DateTimeFormat('es-ES', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      }).format(date);
}
