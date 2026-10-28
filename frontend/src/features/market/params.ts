import type { RankingQuery } from '@/shared/api/client';

export type SortKey = NonNullable<RankingQuery['order_by']>;
export const sortOptions: ReadonlyArray<{ key: SortKey; label: string }> = [
  { key: 'composite_score', label: 'Score' },
  { key: 'confidence', label: 'Cobertura ponderada' },
  { key: 'market_cap', label: 'Capitalización' },
  { key: 'pe', label: 'PER' },
  { key: 'price', label: 'Precio' },
  { key: 'name', label: 'Empresa' },
  { key: 'value_score', label: 'Bloque valor' },
  { key: 'quality_score', label: 'Bloque calidad' },
  { key: 'momentum_score', label: 'Bloque momentum' },
  { key: 'risk_score', label: 'Bloque riesgo' },
  { key: 'roe', label: 'ROE' },
  { key: 'debt_to_equity', label: 'Deuda / patrimonio' },
  { key: 'dividend_yield', label: 'Rentabilidad por dividendo' },
  { key: 'momentum_12m', label: 'Momentum 12 m' },
  { key: 'volatility', label: 'Volatilidad' },
  { key: 'next_earnings_days', label: 'Próximos resultados' },
];
function bounded(
  value: string | null,
  fallback: number,
  min: number,
  max: number,
  integer = false,
) {
  const parsed = value === null || value === '' ? fallback : Number(value);
  return Number.isFinite(parsed) &&
    parsed >= min &&
    parsed <= max &&
    (!integer || Number.isInteger(parsed))
    ? parsed
    : fallback;
}
export function rankingParams(
  params: URLSearchParams,
): RankingQuery & { offset: number; limit: number; order_by: SortKey; direction: 'asc' | 'desc' } {
  const key = params.get('order_by');
  const earnings = params.get('earnings');
  return {
    search: (params.get('search') ?? '').slice(0, 100),
    sectors: params.getAll('sectors').slice(0, 11),
    exclude_sectors: params.getAll('exclude_sectors').slice(0, 11),
    earnings: earnings === 'only' || earnings === 'exclude' ? earnings : undefined,
    earnings_days: bounded(params.get('earnings_days'), 7, 0, 90, true),
    min_market_cap: bounded(params.get('min_market_cap'), 0, 0, 1e15),
    golden_cross_only: params.get('golden_cross_only') === 'true',
    hide_no_data: params.get('hide_no_data') !== 'false',
    offset: bounded(params.get('offset'), 0, 0, 1000, true),
    limit: bounded(params.get('limit'), 25, 1, 500, true),
    order_by: sortOptions.find((option) => option.key === key)?.key ?? 'composite_score',
    direction: params.get('direction') === 'asc' ? 'asc' : 'desc',
  };
}
export function patchParams(
  params: URLSearchParams,
  updates: Record<string, string | string[] | null>,
  resetPage = true,
) {
  const next = new URLSearchParams(params);
  Object.entries(updates).forEach(([key, value]) => {
    next.delete(key);
    if (Array.isArray(value)) value.forEach((item) => next.append(key, item));
    else if (value != null && value !== '') next.set(key, value);
  });
  if (resetPage) next.delete('offset');
  return next;
}
