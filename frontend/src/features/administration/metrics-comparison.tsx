import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJobResult } from '@/shared/api/client';
import { useJob } from '@/shared/api/use-job';
import { HowToRead } from '@/shared/ui/how-to-read';
import { formatNumber, formatPercent } from '@/shared/lib/format';
import { DateField, HealthStatus, RunButton, Section, Table } from './data-health';
import type { Row } from './data-health-job';

type Counts = Record<string, number>;
type RoicSummary = {
  companies: number;
  v1_available: number;
  v2_states: Counts;
  v2_reasons: Counts;
  both_available: number;
  spearman: number | null;
  top_quintile_overlap: number | null;
  median_abs_difference: number | null;
  v1_only_reasons: Counts;
  largest_differences: { symbol: string; v1: number; v2: number; difference: number }[];
};
type EvSummary = {
  both_available: number;
  median_relative_difference: number | null;
  share_beyond_tolerance: number | null;
  tolerance: number;
  v2_reasons: Counts;
  largest_differences: { symbol: string; yahoo: number; v2: number; relative: number }[];
};
type Comparison = {
  as_of: string;
  metrics_version: string;
  sector_proxy: string;
  roic: RoicSummary;
  enterprise_value: EvSummary | null;
  ranking: {
    top_n: number;
    spearman: number | null;
    top_overlap: number | null;
    entering: string[];
    leaving: string[];
  } | null;
};

/** Spanish names of the V2 states and reasons; an unknown code is shown as it comes. */
const LABELS: Record<string, string> = {
  computed: 'Calculada',
  absent: 'Ausente',
  stale: 'Desfasada',
  not_applicable: 'No aplica',
  not_meaningful: 'Sin sentido económico',
  financial_sector: 'Banco, aseguradora o REIT',
  no_annual_report: 'Sin 10-K anual en caché',
  no_opening_balance_sheet: 'Sin balance de apertura',
  debt_absent: 'Deuda no presentada',
  debt_stale: 'Deuda de otro ejercicio',
  cash_absent: 'Caja no presentada',
  cash_stale: 'Caja de otro ejercicio',
  equity_absent: 'Patrimonio no presentado',
  operating_income_absent: 'Resultado operativo no presentado',
  operating_income_stale: 'Resultado operativo de otro ejercicio',
  non_positive_invested_capital: 'Capital invertido no positivo',
  no_market_cap: 'Sin capitalización',
};
const pct = (value: number | null | undefined) => formatPercent(value, { digits: 1 });
const points = (value: number | null | undefined) =>
  value == null ? '—' : formatNumber(value * 100, { digits: 1, signed: true }) + ' pp';
const counts = (values: Counts): Row[] =>
  Object.entries(values)
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({ what: LABELS[key] ?? key, companies: value }));

function Cards({ items }: { items: [string, string][] }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="mt-1 text-base font-semibold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Result({ data }: { data: Comparison }) {
  const { roic, enterprise_value: ev, ranking } = data;
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Fecha {data.as_of} · {data.metrics_version} · {data.sector_proxy}.
      </p>
      <h3 className="font-medium">ROIC</h3>
      <Cards
        items={[
          ['Con ambas versiones', `${roic.both_available} de ${roic.companies}`],
          ['Acuerdo de orden (Spearman)', formatNumber(roic.spearman, { digits: 2 })],
          ['Quintil alto compartido', pct(roic.top_quintile_overlap)],
          ['Diferencia mediana', points(roic.median_abs_difference)],
        ]}
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Table
          label="Estado del ROIC V2"
          columns={[
            ['what', 'Estado'],
            ['companies', 'Empresas'],
          ]}
          rows={counts(roic.v2_states)}
        />
        <Table
          label="V1 tenía número y V2 explica por qué no"
          columns={[
            ['what', 'Motivo'],
            ['companies', 'Empresas'],
          ]}
          rows={counts(roic.v1_only_reasons)}
        />
      </div>
      <Table
        label="Mayores diferencias de ROIC"
        columns={[
          ['symbol', 'Empresa'],
          ['v1', 'V1'],
          ['v2', 'V2'],
          ['difference', 'V2 − V1'],
        ]}
        rows={roic.largest_differences.map((row) => ({
          symbol: row.symbol,
          v1: pct(row.v1),
          v2: pct(row.v2),
          difference: points(row.difference),
        }))}
      />
      {ev ? (
        <>
          <h3 className="font-medium">Valor de empresa: Yahoo frente a SEC V2</h3>
          <Cards
            items={[
              ['Con ambos', String(ev.both_available)],
              ['Diferencia mediana', pct(ev.median_relative_difference)],
              [`Fuera de ±${pct(ev.tolerance)}`, pct(ev.share_beyond_tolerance)],
              ['Sin EV V2', String(Object.values(ev.v2_reasons).reduce((a, b) => a + b, 0))],
            ]}
          />
          <Table
            label="Mayores diferencias de valor de empresa"
            columns={[
              ['symbol', 'Empresa'],
              ['relative', 'V2 frente a Yahoo'],
            ]}
            rows={ev.largest_differences.map((row) => ({
              symbol: row.symbol,
              relative: pct(row.relative),
            }))}
          />
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          En una fecha pasada solo se comparan hechos SEC: Yahoo y el ranking en caché no son
          históricos.
        </p>
      )}
      {ranking && (
        <>
          <h3 className="font-medium">Ranking operativo con el ROIC V2</h3>
          <Cards
            items={[
              [`Top-${ranking.top_n} compartido`, pct(ranking.top_overlap)],
              ['Acuerdo de orden (Spearman)', formatNumber(ranking.spearman, { digits: 2 })],
              ['Entrarían', ranking.entering.join(', ') || '—'],
              ['Saldrían', ranking.leaving.join(', ') || '—'],
            ]}
          />
        </>
      )}
    </div>
  );
}

/** «Métricas SEC V2 frente a V1» (#245): an explicit local job; corrected definitions do not prove alpha. */
export function MetricsComparison() {
  const { start, job } = useJob('metrics-comparison');
  const [date, setDate] = useState('');
  const result = useQuery({
    queryKey: ['job', job.data?.id, 'result'],
    queryFn: ({ signal }) => getJobResult(job.data!.id, signal) as Promise<Comparison>,
    enabled: job.data?.status === 'succeeded',
  });
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  return (
    <Section title="Métricas SEC V2 frente a V1">
      <HowToRead>
        La V1 aproxima el ROIC como beneficio neto / (patrimonio + deuda a largo plazo) y, si falta
        la deuda o la caja, la toma como cero. La V2 usa NOPAT sobre capital invertido medio y
        declara cada ausencia. Esta comparación muestra cuánto cambian los datos y el ranking;
        corregir una definición no demuestra que la selección vaya a rendir más.
      </HowToRead>
      <div className="flex flex-wrap items-end gap-3">
        <DateField
          label="Fecha (vacía = hoy; histórico 2010–jul. 2025)"
          value={date}
          min="2010-01-01"
          max="2025-07-31"
          onChange={setDate}
        />
        <RunButton
          running={running}
          onClick={() => start.mutate({ kind: 'metrics_comparison', start: date || null })}
        >
          Comparar métricas
        </RunButton>
      </div>
      <HealthStatus state={{ start, job, result }} failure="No se pudo comparar las métricas." />
      {result.data && <Result data={result.data} />}
    </Section>
  );
}
