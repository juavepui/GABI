import type { RankingQuery } from '@/shared/api/client';

export type SortKey = NonNullable<RankingQuery['order_by']>;
export const sortOptions: ReadonlyArray<{ key: SortKey; label: string }> = [
  { key: 'composite_score', label: 'Score' },
  { key: 'confidence', label: 'Cobertura' },
  { key: 'market_cap', label: 'Capitalización' },
  { key: 'pe', label: 'PER' },
  { key: 'price', label: 'Precio' },
  { key: 'name', label: 'Empresa' },
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
  return {
    search: (params.get('search') ?? '').slice(0, 100),
    sectors: params.getAll('sectors').slice(0, 11),
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
