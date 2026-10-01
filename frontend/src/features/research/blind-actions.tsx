import { lazy, Suspense, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getBlindExport, getBlindPerformance, getBlindRebalance } from '@/shared/api/client';
import type { BlindStatus } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { JobStatus } from './experiment-jobs';
import { useJob } from '@/shared/api/use-job';

const WealthChart = lazy(() =>
  import('./backtest-factor-charts').then((module) => ({ default: module.WealthChart })),
);
const pct = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', {
        maximumFractionDigits: 1,
        minimumFractionDigits: 1,
        signDisplay: 'always',
      }).format(value * 100) + ' %';

function RebalanceResult({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const result = useQuery({
    queryKey: ['research', 'blind-rebalance', jobId],
    queryFn: ({ signal }) => getBlindRebalance(jobId, signal),
  });
  const recorded = result.data?.recorded;
  useEffect(() => {
    if (recorded)
      void queryClient.invalidateQueries({ queryKey: ['research', 'blind-validations'] });
  }, [recorded, queryClient]);
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  const data = result.data;
  return data.recorded ? (
    <p role="status" className="mt-2 text-sm">
      Rebalanceo del {data.rebalance_date} registrado e inmutable — {data.n_positions} posiciones,
      hash {data.record_hash?.slice(0, 12)}…
    </p>
  ) : (
    <p role="status" className="mt-2 text-sm text-amber-700 dark:text-amber-400">
      No registrado: {data.reason}
    </p>
  );
}

function PerformanceResult({ jobId }: { jobId: string }) {
  const result = useQuery({
    queryKey: ['research', 'blind-performance', jobId],
    queryFn: ({ signal }) => getBlindPerformance(jobId, signal),
  });
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  const data = result.data;
  if (!data.revealed)
    return <p className="text-sm">Sigue bloqueada: no hay rendimiento visible.</p>;
  if (data.periods.length === 0)
    return (
      <p className="text-sm">Desbloqueada, pero todavía no hay ningún rebalanceo registrado.</p>
    );
  const points = data.periods.map((period) => ({
    date: period.rebalance_date,
    capital: period.capital,
    capital_spy: period.capital_spy,
  }));
  return (
    <div className="mt-3 space-y-3 text-sm" role="region" aria-label="Rendimiento revelado">
      {data.revealed_through && (
        <p className="text-muted-foreground">
          Calculado hasta la revisión del {data.revealed_through}, como fija el preregistro.
        </p>
      )}
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">Retorno acumulado (estrategia)</dt>
          <dd className="text-xl font-semibold">{pct(data.cumulative)}</dd>
        </div>
        <div className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">Retorno acumulado (SPY)</dt>
          <dd className="text-xl font-semibold">{pct(data.cumulative_spy)}</dd>
        </div>
      </dl>
      <Suspense fallback={<p>Preparando gráfico…</p>}>
        <WealthChart
          points={points}
          series={['capital', 'capital_spy']}
          labels={{ capital: 'Estrategia', capital_spy: 'SPY' }}
        />
      </Suspense>
      <table className="w-full text-left text-xs" aria-label="Periodos revelados">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-2">Rebalanceo</th>
            <th>Retorno</th>
            <th>Retorno SPY</th>
            <th>Capital</th>
            <th>Capital SPY</th>
          </tr>
        </thead>
        <tbody>
          {data.periods.map((period) => (
            <tr key={period.rebalance_date} className="border-b last:border-0">
              <td className="py-1.5">{period.rebalance_date}</td>
              <td>{pct(period.retorno)}</td>
              <td>{pct(period.retorno_spy)}</td>
              <td>{period.capital.toFixed(4)}</td>
              <td>{period.capital_spy.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExportResult({ jobId }: { jobId: string }) {
  const result = useQuery({
    queryKey: ['research', 'blind-export', jobId],
    queryFn: ({ signal }) => getBlindExport(jobId, signal),
  });
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  return (
    <p role="status" className="mt-2 text-sm">
      Exportado como experimento #{result.data.experiment_id} (fase LIVE_FORWARD) en Research Lab.
    </p>
  );
}

export function BlindActions({ item }: { item: BlindStatus }) {
  const rebalance = useJob('blind-rebalance');
  const performance = useJob('blind-performance');
  const exporting = useJob('blind-export');
  const done = (state: ReturnType<typeof useJob>) =>
    state.jobId != null && state.job.data?.status === 'succeeded';
  return (
    <div className="mt-4 space-y-3">
      <div>
        <Button
          variant="outline"
          disabled={!item.rebalance_due || rebalance.start.isPending}
          title={
            item.rebalance_due
              ? 'Reconstruye el ranking de hoy y fija los precios de entrada.'
              : 'Todavía no toca el siguiente rebalanceo o la cadena no está íntegra.'
          }
          onClick={() =>
            rebalance.start.mutate({ kind: 'blind_rebalance', blind: { validation_id: item.id } })
          }
        >
          Registrar rebalanceo de hoy
        </Button>
        <JobStatus state={rebalance} />
        {done(rebalance) && <RebalanceResult jobId={rebalance.jobId!} />}
      </div>
      {item.revealed && (
        <div>
          <div className="flex flex-wrap gap-3">
            <Button
              disabled={performance.start.isPending}
              onClick={() =>
                performance.start.mutate({
                  kind: 'blind_performance',
                  blind: { validation_id: item.id },
                })
              }
            >
              Calcular rendimiento
            </Button>
            <Button
              variant="outline"
              disabled={exporting.start.isPending || exporting.jobId != null}
              onClick={() =>
                exporting.start.mutate({ kind: 'blind_export', blind: { validation_id: item.id } })
              }
            >
              Exportar al Research Lab
            </Button>
          </div>
          <JobStatus state={performance} />
          {done(performance) && <PerformanceResult jobId={performance.jobId!} />}
          <JobStatus state={exporting} />
          {done(exporting) && <ExportResult jobId={exporting.jobId!} />}
        </div>
      )}
    </div>
  );
}
