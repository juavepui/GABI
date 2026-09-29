import type { Metric } from '@/shared/api/generated/types.gen';

const number = (value: number, digits = 2) =>
  new Intl.NumberFormat('es-ES', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
export function metric(value: Metric | undefined, compact = false): string {
  if (value?.value == null) return '—';
  if (value.unit === 'fraction') return number(value.value * 100, 1) + ' %';
  if (value.unit === 'percent') return number(value.value, 1) + ' %';
  if (value.unit === 'count') return number(value.value, 0);
  if (value.unit === 'USD')
    return new Intl.NumberFormat('es-ES', {
      style: 'currency',
      currency: 'USD',
      notation: compact ? 'compact' : 'standard',
      maximumFractionDigits: 2,
    }).format(value.value);
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
