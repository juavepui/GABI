import { describe, expect, it } from 'vitest';
import {
  V3ComparisonResult,
  type V3Comparison,
} from '../src/features/research/backtest-v3-comparison';
import { renderScreen } from './render';

const metrics = (cagr: number, extra = {}) => ({
  start: '2019-01-02',
  end: '2020-01-02',
  initial: 100_000,
  final: 110_000,
  cagr,
  max_drawdown: -0.12,
  ...extra,
});
const run = (cagr: number) => ({
  metrics: metrics(cagr),
  benchmark: metrics(0.09),
  excess_cagr: cagr - 0.09,
  turnover_yearly: 4.5,
  commissions: 200,
  execution_costs: 400,
  dividends: 1500,
  trades: 160,
  partial_trades: 3,
  blocked_orders: 1,
  stale_days: 2,
  min_cash: 0,
});
const policyRun = {
  metrics: metrics(0.08, { contributed: 19_400 }),
  excess_cagr: -0.01,
  max_drawdown_vs_benchmark: 0.02,
  turnover_yearly: 4.1,
  trades: 150,
  costs: 300,
  average_cash_share: 0.04,
};
const result: V3Comparison = {
  start: '2019-01-02',
  end: '2020-01-02',
  options: { mode: 'fast_dev', max_symbols: 50, top_n: 20, months: 3 },
  rebalances: 4,
  sessions: 252,
  truncated: [],
  v2: {
    metrics: metrics(0.1),
    benchmark: metrics(0.09),
    excess_cagr: 0.01,
    commissions: 160,
    spread: 300,
    strict: true,
    skipped: 0,
  },
  v3: { v2_equivalent: run(0.105), base: run(0.1), stress: run(0.09) },
  data: {
    missing: [],
    anomalies: [],
    exits: [
      { symbol: 'OLD', day: '2019-05-01', status: 'series_ended_without_event', strict: false },
    ],
    strict: false,
    bases: { today_splits: 30 },
  },
  policy_248: {
    policy: { max_issuer_weight: 0.1, max_sector_weight: 0.3 },
    rebalances: 4,
    rebalances_capped: 1,
    average_limit_cash: 0.01,
    unknown_sector_rows: 0,
    accounts: {
      small: {
        setup: { initial: 11_000, monthly: 700 },
        costs: { min_order: 100 },
        benchmark: metrics(0.09),
        equal_weight: policyRun,
        limits: policyRun,
      },
    },
  },
};

describe('comparación V2/V3', () => {
  it('muestra los motores, la incertidumbre de salidas y la política de #248', () => {
    const screen = renderScreen(<V3ComparisonResult result={result} />);
    const text = screen.text();
    expect(text).toContain('muestra de 50 (no citable)');
    expect(text).toContain('V3 con costes de V2');
    expect(text).toContain('V3 estrés');
    expect(text).toContain('el resultado no es estricto');
    expect(text).toContain('1 salidas terminales');
    expect(text).toContain('Cuenta pequeña · con límites');
    expect(text).toContain('Los límites actuaron en 1 de 4 rebalanceos');
  });
});
