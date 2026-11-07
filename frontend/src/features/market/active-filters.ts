import { formatCompactMoney } from '@/shared/lib/format';
import { rankingParams } from './params';

export type ActiveFilter = {
  key: string;
  label: string;
  /** What to patch into the URL to remove only this filter. */
  remove: Record<string, string | string[] | null>;
};

/** The Ranking filters in force, in words, each removable on its own (#320). Reads the URL only. */
export function activeFilters(params: URLSearchParams): ActiveFilter[] {
  const query = rankingParams(params);
  const out: ActiveFilter[] = [];
  if (query.search)
    out.push({ key: 'search', label: `Busca «${query.search}»`, remove: { search: null } });
  const sectors = query.sectors ?? [];
  sectors.forEach((sector) =>
    out.push({
      key: 'sector:' + sector,
      label: 'Sector: ' + sector,
      remove: { sectors: sectors.filter((item) => item !== sector) },
    }),
  );
  const excluded = query.exclude_sectors ?? [];
  excluded.forEach((sector) =>
    out.push({
      key: 'exclude:' + sector,
      label: 'Sin el sector ' + sector,
      remove: { exclude_sectors: excluded.filter((item) => item !== sector) },
    }),
  );
  if (query.min_market_cap)
    out.push({
      key: 'cap',
      label: 'Capitalización desde ' + formatCompactMoney(query.min_market_cap),
      remove: { min_market_cap: null },
    });
  if (query.earnings) {
    const days = query.earnings_days === 1 ? '1 día' : `${query.earnings_days} días`;
    out.push({
      key: 'earnings',
      label:
        query.earnings === 'only'
          ? `Presentan resultados en los próximos ${days}`
          : `Sin resultados en los próximos ${days}`,
      remove: { earnings: null, earnings_days: null },
    });
  }
  if (query.golden_cross_only)
    out.push({
      key: 'golden',
      label: 'Con cruce dorado reciente',
      remove: { golden_cross_only: null },
    });
  if (!query.hide_no_data)
    out.push({
      key: 'no_data',
      label: 'Incluye empresas sin datos',
      remove: { hide_no_data: null },
    });
  return out;
}
