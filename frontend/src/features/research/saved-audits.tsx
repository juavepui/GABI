import { useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getSavedAudits,
  getSavedBlockBootstrap,
  getSavedFactorBenchmark,
  getSavedFactorStability,
  getSavedOverfitting,
  getSavedRankStability,
  savedAuditFile,
} from '@/shared/api/client';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { Benchmark, Stability } from './backtest-factors';
import { BlockBootstrapResult } from './block-bootstrap-view';
import { formatNumber, formatPercent } from '@/shared/lib/format';

const pct = (value: number | null | undefined, digits = 1) =>
  formatPercent(value, { digits, fixed: true });
const num = (value: number | null | undefined, digits = 3) => formatNumber(value, { digits });

function Section({
  title,
  open = false,
  children,
}: {
  title: string;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="rounded-xl border bg-card p-5 text-sm" open={open}>
      <summary className="cursor-pointer font-medium">{title}</summary>
      <div className="mt-3 space-y-3">{children}</div>
    </details>
  );
}

function Overfitting() {
  const query = useQuery({
    queryKey: ['research', 'saved', 'overfitting'],
    queryFn: ({ signal }) => getSavedOverfitting(signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  return (
    <div role="region" aria-label="Auditoría de sobreajuste" className="space-y-3">
      <dl className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">PBO · variantes a coste fijo</dt>
          <dd className="text-xl font-semibold">{pct(data.pbo)}</dd>
        </div>
        <div className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">DSR · Top-20 trimestral</dt>
          <dd className="text-xl font-semibold">{pct(data.dsr)}</dd>
        </div>
        <div className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">Variantes / trimestres</dt>
          <dd className="text-xl font-semibold">
            {data.n_trials} / {data.n_obs}
          </dd>
        </div>
      </dl>
      <p className="text-xs text-muted-foreground">
        Reconstrucción V1 con muestra de {data.max_symbols} empresas, semilla 42. La matriz completa
        conserva también los ensayos de sensibilidad a costes. Sharpe aritmético de excesos, RF
        anual 4 %, observaciones trimestrales para todas las frecuencias.
      </p>
      <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-amber-800 dark:text-amber-300">
        Auditoría parcial de investigación: faltan ensayos con parámetros originales no
        recuperables. PBO evalúa elegir el mejor Sharpe; la elección histórica también miró
        drawdown. DSR usa el número nominal de variantes correlacionadas y no constituye validación
        prospectiva.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs" aria-label="Ensayos retrospectivos">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Ensayo</th>
              <th>Tipo</th>
              <th>Rebalanceo (meses)</th>
              <th>Coste (pb/lado)</th>
              <th>Sharpe aritmético</th>
            </tr>
          </thead>
          <tbody>
            {data.trials.map((trial) => (
              <tr key={trial.trial_id} className="border-b last:border-0">
                <td className="py-1.5">{trial.trial_id}</td>
                <td>{trial.role}</td>
                <td>{trial.months}</td>
                <td>{num(trial.cost_bps, 1)}</td>
                <td>{num(trial.sharpe)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Sensibilidad PBO a bloques de igual tamaño:{' '}
        {data.pbo_sensitivity.map((item) => `${item.splits} bloques: ${pct(item.pbo)}`).join('; ')}
      </p>
      <ul className="space-y-1 text-xs text-muted-foreground">
        {data.excluded.map((item) => (
          <li key={item.trial}>
            Fuera de la matriz — {item.trial}: {item.reason}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-4">
        <a
          className="text-primary underline"
          href={savedAuditFile('overfitting-audit', 'returns.csv')}
          download
        >
          Descargar matriz completa
        </a>
        <a
          className="text-primary underline"
          href={savedAuditFile('overfitting-audit', 'audit.json')}
          download
        >
          Descargar informe y procedencia
        </a>
      </div>
    </div>
  );
}

function SavedBenchmark() {
  const query = useQuery({
    queryKey: ['research', 'saved', 'factor-benchmark'],
    queryFn: ({ signal }) => getSavedFactorBenchmark(signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return (
    <>
      <p className="text-xs text-muted-foreground">
        V1 Top-20 trimestral, N=200, semilla 42, pesos 30/35/25/10, coste 10 pb/lado.
      </p>
      <Benchmark audit={query.data} />
      <div className="flex flex-wrap gap-4">
        {(['expanding', 'in_sample'] as const).map((mode) => (
          <a
            key={mode}
            className="text-primary underline"
            href={savedAuditFile('factor-benchmark', `${mode}-curves.csv`)}
            download
          >
            Descargar curvas ({mode === 'expanding' ? 'expansiva' : 'muestra completa'})
          </a>
        ))}
        <a
          className="text-primary underline"
          href={savedAuditFile('factor-benchmark', 'audit.json')}
          download
        >
          Descargar benchmark completo
        </a>
      </div>
    </>
  );
}

function SavedStability() {
  const query = useQuery({
    queryKey: ['research', 'saved', 'factor-stability'],
    queryFn: ({ signal }) => getSavedFactorStability(signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return (
    <>
      <p className="text-xs text-muted-foreground">
        Recálculo V1 Top-20 trimestral, muestra de 200 empresas, semilla 42, pesos 30/35/25/10 y
        coste de 10 pb por lado. Inputs de la auditoría HAC de septiembre de 2026.
      </p>
      <Stability audit={query.data} />
      <div className="flex flex-wrap gap-4">
        <a
          className="text-primary underline"
          href={savedAuditFile('factor-stability', 'coefficients.csv')}
          download
        >
          Descargar coeficientes e intervalos
        </a>
        <a
          className="text-primary underline"
          href={savedAuditFile('factor-stability', 'audit.json')}
          download
        >
          Descargar diagnóstico completo
        </a>
      </div>
    </>
  );
}

function SavedBootstrap() {
  const [dataset, setDataset] = useState('');
  const query = useQuery({
    queryKey: ['research', 'saved', 'block-bootstrap', dataset],
    queryFn: ({ signal }) => getSavedBlockBootstrap(dataset, signal),
    placeholderData: (previous) => previous,
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  return (
    <>
      {data.unavailable.map((item) => (
        <p key={item.id} className="text-muted-foreground">
          {item.label} no estimable: {item.reason}
        </p>
      ))}
      <label className="grid w-fit gap-1">
        Series del diagnóstico
        <NativeSelect value={data.selected} onChange={(event) => setDataset(event.target.value)}>
          {data.datasets.map((item) => (
            <NativeSelectOption key={item.id} value={item.id}>
              {item.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </label>
      <BlockBootstrapResult
        key={data.selected}
        view={data.view}
        downloads={{
          json: savedAuditFile('block-bootstrap', 'resultado.json'),
          csv: savedAuditFile('block-bootstrap', `${data.selected}-distributions.csv`),
        }}
      />
    </>
  );
}

function SavedRankStability() {
  const [date, setDate] = useState('');
  const query = useQuery({
    queryKey: ['research', 'saved', 'rank-stability', date],
    queryFn: ({ signal }) => getSavedRankStability(date, signal),
    placeholderData: (previous) => previous,
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  return (
    <div role="region" aria-label="Estabilidad histórica del ranking" className="space-y-3">
      <p className="text-xl font-semibold">
        Persistencia media del Top-20 · {data.n_dates} fechas: {num(data.stability_score, 1)} %
      </p>
      <p className="text-xs text-muted-foreground">
        Diagnóstico retrospectivo sin leer rentabilidades. No valida capacidad predictiva ni
        modifica el modelo.
      </p>
      <table className="text-left text-xs" aria-label="Métricas agregadas">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-2 pr-6">Métrica</th>
            <th className="pr-6">Media</th>
            <th className="pr-6">Mínimo</th>
            <th>Máximo</th>
          </tr>
        </thead>
        <tbody>
          {data.aggregate.map((row) => (
            <tr key={row.metric} className="border-b last:border-0">
              <td className="py-1.5 pr-6">{row.metric}</td>
              <td className="pr-6">{num(row.mean, 4)}</td>
              <td className="pr-6">{num(row.min, 4)}</td>
              <td>{num(row.max, 4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <label className="grid w-fit gap-1">
        Fecha del ranking
        <NativeSelect value={data.selected} onChange={(event) => setDate(event.target.value)}>
          {data.dates.map((item) => (
            <NativeSelectOption key={item} value={item}>
              {item}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </label>
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-left text-xs" aria-label="Dispersión por empresa">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Símbolo</th>
              <th>Posición</th>
              <th>Mejor</th>
              <th>Peor</th>
              <th>Desv. típica</th>
              <th>Top-10</th>
              <th>Top-20</th>
              <th>Top-30</th>
              <th>Diagnóstico</th>
            </tr>
          </thead>
          <tbody>
            {data.companies.map((row) => (
              <tr key={row.symbol} className="border-b last:border-0">
                <td className="py-1">{row.symbol}</td>
                <td>{num(row.base_rank, 0)}</td>
                <td>{num(row.rank_min, 0)}</td>
                <td>{num(row.rank_max, 0)}</td>
                <td>{num(row.rank_std, 2)}</td>
                <td>{pct(row.top10_inclusion, 0)}</td>
                <td>{pct(row.top20_inclusion, 0)}</td>
                <td>{pct(row.top30_inclusion, 0)}</td>
                <td>{row.diagnosis ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!data.sectors_complete && (
        <p className="text-muted-foreground">
          Faltan sectores históricos: la concentración sectorial no está acreditada.
        </p>
      )}
    </div>
  );
}

export function SavedAudits() {
  const overview = useQuery({
    queryKey: ['research', 'saved'],
    queryFn: ({ signal }) => getSavedAudits(signal),
  });
  if (overview.isPending) return <LoadingState />;
  if (overview.isError)
    return <ErrorState error={overview.error} retry={() => void overview.refetch()} />;
  const available = overview.data;
  return (
    <section className="space-y-3" aria-label="Auditorías guardadas">
      <h2 className="text-lg font-semibold">Auditorías guardadas</h2>
      <p className="text-sm text-muted-foreground">
        Resultados publicados en el repositorio, verificados por su huella antes de mostrarse. No se
        recalculan ni se modifican desde esta pantalla.
      </p>
      {available.overfitting_audit && (
        <Section title="Auditoría retrospectiva de las configuraciones documentadas" open>
          <Overfitting />
        </Section>
      )}
      {available.factor_benchmark && (
        <Section title="Benchmark ajustado por beta/factores · auditoría guardada">
          <SavedBenchmark />
        </Section>
      )}
      {available.factor_stability && (
        <Section title="Estabilidad temporal FF5 + Momentum · auditoría guardada">
          <SavedStability />
        </Section>
      )}
      {available.block_bootstrap && (
        <Section title="Incertidumbre por bloques · diagnóstico guardado">
          <SavedBootstrap />
        </Section>
      )}
      {available.rank_stability && (
        <Section title="Estabilidad histórica · vecindad preregistrada de pesos">
          <SavedRankStability />
        </Section>
      )}
    </section>
  );
}
