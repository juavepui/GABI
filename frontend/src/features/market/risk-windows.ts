import { useQuery } from '@tanstack/react-query';
import { getRiskWindows } from '@/shared/api/client';
import type { DrawdownWindow, RiskWindows } from '@/shared/api/generated/types.gen';
import { formatPercent } from '@/shared/lib/format';

const MONTH = new Intl.DateTimeFormat('es-ES', {
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});
const month = (value: string | null | undefined) => (value ? MONTH.format(new Date(value)) : '—');

export const WINDOW_LABELS: Record<DrawdownWindow['window'], string> = {
  full: 'todo el histórico',
  '5y': '5 años',
  '3y': '3 años',
};

/** Window, peak and trough of every drawdown, as the backend dates them (#175). */
export function useRiskWindows(symbols: string[]) {
  return useQuery({
    queryKey: ['market', 'risk-windows', symbols],
    queryFn: ({ signal }) => getRiskWindows(symbols, signal),
    enabled: symbols.length > 0,
  });
}

export function drawdownOf(item: RiskWindows | undefined, window: DrawdownWindow['window']) {
  return item?.drawdowns.find((row) => row.window === window);
}

/** «pico jun 2014 → valle mar 2020», or why there is no fall to date. */
export function drawdownDates(row: DrawdownWindow | undefined): string {
  if (!row || row.value == null) return '';
  if (row.value === 0) return 'sin caídas en la ventana';
  return `pico ${month(row.peak_date)} → valle ${month(row.trough_date)}`;
}

/** «desde mar 2006 (5.180 sesiones)»: the history the whole-history figures use. */
export function historySpan(item: RiskWindows | undefined): string {
  if (!item?.history_start) return '';
  return `desde ${month(item.history_start)} (${item.sessions.toLocaleString('es-ES')} sesiones)`;
}

export function drawdownValue(row: DrawdownWindow | undefined): string {
  if (!row || row.value == null) return '—';
  return formatPercent(row.value) + (row.complete ? '' : ' *');
}
