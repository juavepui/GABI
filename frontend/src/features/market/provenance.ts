import type { ChecklistAlternative, MetricSource } from '@/shared/api/generated/types.gen';

/** Labels of the source and period the backend declares for each value (#169); nothing is inferred here. */
const SOURCES: Record<MetricSource['source'], string> = {
  yahoo: 'Yahoo',
  sec_10k: 'SEC 10-K',
  prices: 'GABI con precios en caché',
};

const PERIODS: Record<MetricSource['period'] | ChecklistAlternative['period'], string> = {
  ttm: '12 meses',
  mrq: 'último trimestre',
  snapshot: 'dato actual',
  '5y_monthly': '5 años, mensual',
  '3m': 'media de 3 meses',
  fiscal_year: 'último ejercicio',
  fiscal_years_3: '3 ejercicios',
  '6m': '6 meses',
  '12m': '12 meses',
  cached_history: 'todo el histórico',
};

const APPROXIMATIONS: Record<NonNullable<MetricSource['approximation']>, string> = {
  net_income_over_equity_plus_long_term_debt:
    'aproximado: beneficio neto / (patrimonio + deuda LP)',
};

export function sourceLabel(
  value:
    | (Pick<MetricSource, 'source' | 'period'> & Partial<Pick<MetricSource, 'approximation'>>)
    | undefined,
): string {
  if (!value) return '';
  const label = `${SOURCES[value.source]} · ${PERIODS[value.period]}`;
  return value.approximation ? `${label} · ${APPROXIMATIONS[value.approximation]}` : label;
}
