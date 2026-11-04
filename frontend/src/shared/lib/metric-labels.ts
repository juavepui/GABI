// The 13 scored metrics (scoring.SCORE_METRICS), with the labels of the old pages.
export const METRIC_LABELS: Record<string, string> = {
  pe: 'PER',
  pb: 'Precio / valor contable',
  ev_ebitda: 'EV/EBITDA',
  roic: 'ROIC',
  operating_margin: 'Margen operativo',
  revenue_cagr_3y: 'Crecimiento de ventas (3 años)',
  fcf_cagr_3y: 'Crecimiento de la caja libre (3 años)',
  momentum_12m: 'Subida en 12 meses',
  rel_strength_6m: 'Subida frente al mercado (6 meses)',
  price_vs_sma200: 'Precio frente a su media de 200 días',
  debt_to_equity: 'Deuda/Patrimonio',
  volatility: 'Volatilidad anualizada (todo el histórico)',
  max_drawdown: 'Caída máxima (todo el histórico)',
};

/** Spanish name of a scored metric; an unknown key is shown as it comes. */
export const metricLabel = (metric: string) => METRIC_LABELS[metric] ?? metric;
