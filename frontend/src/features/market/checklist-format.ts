import type { ChecklistCriterion } from '@/shared/api/generated/types.gen';
import { formatCompactMoney, formatNumber, formatPercent } from '@/shared/lib/format';

type Unit = ChecklistCriterion['unit'];

/** Presentation of a value in its contract unit; the backend computes every value and verdict. */
export function show(value: number | null | undefined, unit: Unit): string {
  if (unit === 'fraction') return formatPercent(value);
  if (unit === 'USD') return formatCompactMoney(value);
  if (unit === 'count') return formatNumber(value, { digits: 0 });
  return value == null ? '—' : formatNumber(value, { digits: 2 }) + 'x';
}

export const CONCEPTS: Record<string, string> = {
  revenue: 'ingresos',
  net_income: 'beneficio neto',
  ocf: 'flujo operativo',
  capex: 'CAPEX',
  gross_profit: 'beneficio bruto',
  operating_income: 'resultado operativo',
  interest: 'gastos por intereses',
  sbc: 'remuneración en acciones',
  lt_debt: 'deuda a largo plazo',
  cash: 'caja',
  goodwill: 'goodwill',
  assets: 'activos totales',
  dividends: 'dividendos pagados',
  debt_issuance: 'emisión de deuda',
  lt_debt_current: 'deuda a largo con vencimiento corto',
  short_borrowings: 'préstamos a corto',
  short_investments: 'inversiones a corto',
  debt_current: 'deuda a corto',
};
const REASONS: Record<string, string> = {
  not_captured: 'Yahoo no informa este dato o aún no se ha refrescado',
  no_debt_reported: 'La SEC no tiene deuda declarada; no se asume cero',
  no_debt: 'Sin deuda: cumple',
  financial_sector: 'No aplica a bancos y aseguradoras',
  no_price: 'Sin precio en la caché',
  no_shares: 'Sin número de acciones SEC',
  no_forward_eps: 'Sin BPA estimado (consenso)',
  non_positive_net_income: 'Beneficio neto ≤ 0',
  non_positive_start_or_end_value: 'Valor inicial o final ≤ 0',
  non_positive_invested_capital: 'Capital invertido ≤ 0',
  non_positive_fcf: 'FCF ≤ 0',
  no_effective_tax_rate: 'Sin tipo impositivo efectivo',
  no_ebitda: 'Sin EBITDA positivo',
  no_ebit: 'Sin EBIT positivo',
  no_fcf: 'Sin FCF positivo',
  no_gross_profit: 'Sin beneficio bruto ni coste de ventas',
  no_beta: 'Sin beta calculada frente al SPY',
  missing_component: 'Falta algún componente del mismo ejercicio',
  too_few_years: 'Pocos ejercicios consecutivos',
  no_insider_data: 'Sin operaciones Form 4 en la caché',
  no_buybacks_reported: 'Sin recompras declaradas',
  no_historical_growth: 'Sin crecimiento histórico del CFO',
  below_search_range: 'El precio descuenta un crecimiento inferior al −50 %',
  above_search_range: 'El precio descuenta un crecimiento superior al 100 %',
  gaap_ebitda: 'GABI calcula el EBITDA con cifras GAAP; el EV/EBITDA del ranking es el de Yahoo',
  invalid_saved_thresholds: 'Los umbrales guardados no son válidos; se usan los del Excel',
  not_in_universe: 'La empresa no está en el universo actual',
  share_basis_mismatch:
    'Las acciones SEC no cuadran con el precio (varias clases de acciones, split sin registrar o emisión reciente)',
};

export function reasonText(reason: string | null | undefined): string {
  if (!reason) return '';
  if (REASONS[reason]) return REASONS[reason];
  const stale = /^stale_(.+)$/.exec(reason);
  if (stale) return `Dato de ${CONCEPTS[stale[1]] ?? stale[1]} de otro ejercicio`;
  const absent = /^no_(.+)$/.exec(reason);
  if (absent) return `Sin dato SEC de ${CONCEPTS[absent[1]] ?? absent[1]}`;
  if (/^fewer_than_\d+_peers$/.test(reason)) return 'Pocos pares con dato';
  if (/^(fewer_than|no_shares|no_margin)/.test(reason)) return 'Histórico insuficiente';
  return reason;
}

export const VERDICTS: Record<
  ChecklistCriterion['verdict'],
  { label: string; variant: 'default' | 'destructive' | 'outline' | 'secondary' }
> = {
  pass: { label: '✔ Cumple', variant: 'default' },
  fail: { label: '✘ No cumple', variant: 'destructive' },
  missing: { label: 'Sin dato', variant: 'outline' },
  not_applicable: { label: 'No aplica', variant: 'secondary' },
  info: { label: 'Info', variant: 'secondary' },
};
