import type { ReactNode } from 'react';
import { dateText, formatNumber, formatPercent } from '@/shared/lib/format';
import { HowToRead } from '@/shared/ui/how-to-read';

type Metrics = {
  start: string;
  end: string;
  initial: number;
  final: number;
  cagr: number | null;
  max_drawdown: number | null;
  contributed?: number;
};
type V3Run = {
  metrics: Metrics;
  benchmark: Metrics;
  excess_cagr: number | null;
  turnover_yearly: number | null;
  commissions: number;
  execution_costs: number;
  dividends: number;
  trades: number;
  partial_trades: number;
  blocked_orders: number;
  stale_days: number;
  min_cash: number;
};
type PolicyRun = {
  metrics: Metrics;
  excess_cagr: number | null;
  max_drawdown_vs_benchmark: number | null;
  turnover_yearly: number | null;
  trades: number;
  costs: number;
  average_cash_share: number | null;
};
type Account = {
  setup: { initial: number; monthly: number };
  costs: { min_order: number };
  benchmark: Metrics;
  equal_weight: PolicyRun;
  limits: PolicyRun;
};
export type V3Comparison = {
  start: string;
  end: string;
  options: { mode: string; max_symbols: number | null; top_n: number; months: number };
  rebalances: number;
  sessions: number;
  truncated: string[];
  v2: {
    metrics: Metrics;
    benchmark: Metrics;
    excess_cagr: number | null;
    commissions: number;
    spread: number;
    strict: boolean;
    skipped: number;
  };
  v3: Record<string, V3Run>;
  data: {
    missing: string[];
    anomalies: { symbol: string; day: string; kind: string }[];
    exits: { symbol: string; day: string; status: string; strict: boolean }[];
    strict: boolean;
    bases: Record<string, number>;
  };
  policy_248: {
    policy: { max_issuer_weight: number; max_sector_weight: number };
    rebalances: number;
    rebalances_capped: number;
    average_limit_cash: number;
    unknown_sector_rows: number;
    accounts: Record<string, Account>;
  };
};

const pct = (value: number | null | undefined) => formatPercent(value, { digits: 1 });
const points = (value: number | null | undefined) =>
  value == null ? '—' : formatNumber(value * 100, { digits: 1, signed: true }) + ' pp';
const money = (value: number | null | undefined) => formatNumber(value, { digits: 0 }) + ' $';
const SCENARIOS: Record<string, string> = {
  v2_equivalent: 'V3 con costes de V2',
  base: 'V3 base',
  stress: 'V3 estrés',
};
const ACCOUNTS: Record<string, string> = { large: 'Cuenta grande', small: 'Cuenta pequeña' };

function Grid({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            {head.map((label, index) => (
              <th key={label} className={index === 0 ? 'py-2' : undefined}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b last:border-0">
              {row.map((cell, column) => (
                <td key={column} className={column === 0 ? 'py-2' : 'tabular-nums'}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** V2/V3 comparison and #248 validation (#249): an engine diagnostic, never evidence of an advantage. */
export function V3ComparisonResult({ result }: { result: V3Comparison }) {
  const { v2, v3, data, policy_248: policy } = result;
  const sample = result.options.mode !== 'validation';
  return (
    <section className="space-y-5 rounded-xl border bg-card p-5" aria-label="Comparación V2 y V3">
      <div>
        <h3 className="text-xl font-semibold">
          V2 frente a V3 · {dateText(result.start)} a {dateText(result.end)}
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          {result.rebalances} rebalanceos de V2 · {result.options.top_n} empresas ·{' '}
          {sample ? `muestra de ${result.options.max_symbols} (no citable)` : 'universo completo'}
        </p>
        <HowToRead className="mt-2">
          V3 ejecuta exactamente las selecciones que decidió V2, con los mismos datos: señal al
          cierre, ejecución en la apertura siguiente a precio nominal, costes dentro de la caja,
          splits y dividendos como eventos y salidas explícitas. La diferencia mide el motor, no la
          estrategia: es un diagnóstico y no demuestra ventaja frente al S&amp;P 500.
        </HowToRead>
        {(!v2.strict || !data.strict) && (
          <p className="mt-2 text-sm text-destructive">
            Alguna posición dejó de cotizar sin evento terminal confirmado y se liquidó a su último
            precio: el resultado no es estricto.
          </p>
        )}
      </div>
      <Grid
        head={[
          'Motor',
          'Anualizado',
          'Benchmark',
          'Exceso',
          'Máx. drawdown',
          'Capital final',
          'Costes',
        ]}
        rows={[
          [
            'V2',
            pct(v2.metrics.cagr),
            pct(v2.benchmark.cagr),
            points(v2.excess_cagr),
            pct(v2.metrics.max_drawdown),
            money(v2.metrics.final),
            money(v2.commissions + v2.spread),
          ],
          ...Object.entries(v3).map(([name, run]) => [
            SCENARIOS[name] ?? name,
            pct(run.metrics.cagr),
            pct(run.benchmark.cagr),
            points(run.excess_cagr),
            pct(run.metrics.max_drawdown),
            money(run.metrics.final),
            money(run.commissions + run.execution_costs),
          ]),
        ]}
      />
      <Grid
        head={[
          'Ejecución V3',
          'Operaciones',
          'Parciales o reducidas',
          'Bloqueadas',
          'Días con precio desfasado',
          'Rotación anual',
          'Caja mínima',
        ]}
        rows={Object.entries(v3).map(([name, run]) => [
          SCENARIOS[name] ?? name,
          run.trades,
          run.partial_trades,
          run.blocked_orders,
          run.stale_days,
          formatNumber(run.turnover_yearly, { digits: 2 }) + '×',
          money(run.min_cash),
        ])}
      />
      <p className="text-xs text-muted-foreground">
        Datos:{' '}
        {Object.entries(data.bases)
          .map(
            ([basis, count]) =>
              `${count} series ${basis === 'today_splits' ? 'Yahoo (splits deshechos)' : 'de archivo'}`,
          )
          .join(' · ')}{' '}
        · {data.exits.length} salidas terminales · {data.anomalies.length} anomalías de ajuste sin
        pagar · {data.missing.length} sin serie
        {data.missing.length ? ` (${data.missing.slice(0, 10).join(', ')})` : ''}
        {result.truncated.length > 0 && ` · listas recortadas: ${result.truncated.join(', ')}`}
      </p>
      <div>
        <h3 className="font-semibold">Política invertible de #248</h3>
        <HowToRead className="mt-2">
          La misma selección en pesos iguales frente a la política con límites (emisor ≤{' '}
          {pct(policy.policy.max_issuer_weight)}, sector ≤ {pct(policy.policy.max_sector_weight)};
          lo que no cabe queda en caja). La cuenta pequeña aporta cada mes y esas aportaciones
          esperan al siguiente rebalanceo; el benchmark las invierte al día siguiente. Con
          aportaciones, la rentabilidad y el drawdown están ponderados en el tiempo. Los límites
          actuaron en {policy.rebalances_capped} de {policy.rebalances} rebalanceos.
        </HowToRead>
      </div>
      <Grid
        head={[
          'Cuenta y reparto',
          'Anualizado',
          'Exceso',
          'Máx. drawdown',
          'Rotación anual',
          'Costes',
          'Caja media',
          'Final / aportado',
        ]}
        rows={Object.entries(policy.accounts).flatMap(([name, account]) =>
          (['equal_weight', 'limits'] as const).map((key) => {
            const run = account[key];
            return [
              `${ACCOUNTS[name] ?? name} · ${key === 'limits' ? 'con límites' : 'pesos iguales'}`,
              pct(run.metrics.cagr),
              points(run.excess_cagr),
              pct(run.metrics.max_drawdown),
              formatNumber(run.turnover_yearly, { digits: 2 }) + '×',
              money(run.costs),
              pct(run.average_cash_share),
              `${money(run.metrics.final)} / ${money(run.metrics.contributed ?? run.metrics.initial)}`,
            ];
          }),
        )}
      />
      <p className="text-xs text-muted-foreground">
        {Object.entries(policy.accounts)
          .map(
            ([name, account]) =>
              `${ACCOUNTS[name] ?? name}: ${money(account.setup.initial)} iniciales${account.setup.monthly ? ` y ${money(account.setup.monthly)} al mes` : ''}, orden mínima ${money(account.costs.min_order)}, benchmark ${pct(account.benchmark.cagr)} anual`,
          )
          .join(' · ')}
        .
      </p>
    </section>
  );
}
