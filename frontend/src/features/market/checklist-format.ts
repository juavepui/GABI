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
  no_price: 'No hay precio guardado',
  no_shares: 'La SEC no da el número de acciones',
  no_forward_eps: 'Sin previsión de beneficio por acción de los analistas',
  non_positive_net_income: 'La empresa no tiene beneficios (pierde dinero o gana cero)',
  non_positive_start_or_end_value: 'El valor inicial o final es cero o negativo',
  non_positive_invested_capital: 'El capital invertido es cero o negativo',
  non_positive_fcf: 'No genera caja libre (FCF cero o negativo)',
  no_effective_tax_rate: 'No se conoce el porcentaje de impuestos que paga',
  no_ebitda: 'Su beneficio antes de intereses, impuestos y amortizaciones (EBITDA) no es positivo',
  no_ebit: 'Su beneficio de explotación (EBIT) no es positivo',
  no_fcf: 'No genera caja libre (FCF) positiva',
  no_gross_profit: 'Sin beneficio bruto ni coste de ventas',
  no_beta: 'No se ha podido calcular cuánto se mueve con el mercado (beta)',
  missing_component: 'Falta alguno de los datos necesarios del mismo año',
  too_few_years: 'Hay pocos años seguidos de datos',
  no_insider_data: 'No hay guardadas compras o ventas de sus directivos (formulario 4 de la SEC)',
  no_buybacks_reported: 'Sin recompras declaradas',
  no_historical_growth: 'No se conoce cuánto ha crecido su caja de las operaciones (CFO)',
  below_search_range: 'El precio descuenta un crecimiento inferior al −50 %',
  above_search_range: 'El precio descuenta un crecimiento superior al 100 %',
  gaap_ebitda:
    'GABI calcula el EBITDA con las cifras oficiales de las cuentas; el EV/EBITDA del ranking es el de Yahoo y puede no coincidir',
  invalid_saved_thresholds: 'Los umbrales guardados no son válidos; se usan los de por defecto',
  not_in_universe: 'La empresa no está en la lista actual del S&P 500',
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
  if (/^fewer_than_\d+_peers$/.test(reason)) return 'Pocas empresas parecidas con dato';
  if (/^(fewer_than|no_shares|no_margin)/.test(reason)) return 'No hay suficientes años de datos';
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
