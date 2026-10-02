import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { cancelJob, createJob, getHistoricalOutcomes, getJob } from '@/shared/api/client';
import type { OutcomeResult } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatPercent } from '@/shared/lib/format';
import { ResearchModeNotice } from '@/shared/ui/research-mode';

const signedPct = (value: number | null | undefined) =>
  value == null ? '—' : (value > 0 ? '+' : '') + formatPercent(value, { digits: 1, fixed: true });

function OutcomeLine({ label, outcome }: { label: string; outcome: OutcomeResult }) {
  if (outcome.status === 'reserved') {
    return (
      <li>
        {label}: <strong>reservado</strong>. La ventana acaba el {outcome.end_date} y sus precios
        pertenecen al periodo posterior al corte observado; no se consultan.
      </li>
    );
  }
  if (outcome.status === 'pending') {
    return (
      <li>
        {label}: pendiente hasta {outcome.end_date}
      </li>
    );
  }
  return (
    <li>
      {label}: candidatas {signedPct(outcome.portfolio_return)} · SPY{' '}
      {signedPct(outcome.benchmark_return)} · cobertura {outcome.available}/{outcome.requested}
      {outcome.status === 'incomplete' && (outcome.missing ?? []).length > 0 && (
        <span className="block text-xs text-muted-foreground">
          Resultado parcial; faltan: {(outcome.missing ?? []).join(', ')}
        </span>
      )}
    </li>
  );
}

export function HistoricalOutcomes({
  rankingJobId,
  researchAllowed,
}: {
  rankingJobId: string;
  researchAllowed: boolean;
}) {
  const [topN, setTopN] = useState(10);
  const [cost, setCost] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'historical_outcomes',
        outcomes: { source_job_id: rankingJobId, top_n: topN, cost_bps: cost },
        idempotency_key: 'outcomes:' + crypto.randomUUID(),
      }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const result = useQuery({
    queryKey: ['research', 'historical-outcomes', jobId],
    queryFn: ({ signal }) => getHistoricalOutcomes(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });
  const data = result.data;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJobId(null);
    run.mutate();
  }

  return (
    <section
      className="space-y-3 rounded-xl border bg-card p-5 text-sm"
      aria-label="Resultado posterior de las primeras candidatas"
    >
      <h3 className="text-lg font-semibold">Resultado posterior de las primeras candidatas</h3>
      <p className="text-xs text-muted-foreground">
        Reconstrucción exploratoria con rentabilidad total ajustada por dividendos, cartera
        equiponderada y SPY. Los símbolos sin precio completo se excluyen y se indican. Solo se
        calculan horizontes cuyos precios quedan dentro del periodo observado hasta el 2025-07-02.
      </p>
      {!researchAllowed && <ResearchModeNotice action="Calcular retornos posteriores" />}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium">
          Primeras candidatas
          <Input
            className="mt-1.5 w-28"
            type="number"
            min={1}
            max={50}
            value={topN}
            onChange={(event) => setTopN(Number(event.target.value))}
            required
          />
        </label>
        <label className="text-xs font-medium">
          Coste por operación (puntos básicos)
          <Input
            className="mt-1.5 w-28"
            type="number"
            min={0}
            max={100}
            step={0.5}
            value={cost}
            onChange={(event) => setCost(Number(event.target.value))}
            required
          />
        </label>
        <Button type="submit" disabled={run.isPending || !researchAllowed}>
          Evaluar resultado posterior
        </Button>
      </form>
      {run.isError && <ErrorState error={run.error} retry={() => run.mutate()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <p className="text-muted-foreground">
          Evaluación #{job.data.id.slice(0, 8)} · {job.data.phase} · {job.data.status}
          {['queued', 'running'].includes(job.data.status) && (
            <Button
              className="ml-3"
              size="sm"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Solicitar cancelación
            </Button>
          )}
        </p>
      )}
      {job.data?.status === 'failed' && (
        <p className="text-destructive">La evaluación no terminó. Revisa los datos locales.</p>
      )}
      {result.isPending && job.data?.status === 'succeeded' && <LoadingState />}
      {result.isError && <ErrorState error={result.error} retry={() => void result.refetch()} />}
      {data && (
        <div className="space-y-4">
          {data.candidates.length < data.top_n && (
            <p className="text-xs text-muted-foreground">
              Solo {data.candidates.length} candidatas tienen score.
            </p>
          )}
          <ul className="space-y-1">
            {data.horizons.map((outcome) => (
              <OutcomeLine
                key={outcome.months}
                label={`${outcome.months} meses`}
                outcome={outcome}
              />
            ))}
          </ul>
          <div>
            <h4 className="font-semibold">Comparar qué bloque aporta más en esta fecha</h4>
            <p className="text-xs text-muted-foreground">
              Comparación exploratoria de una sola fecha a 12 meses. Para ajustar pesos hacen falta
              varias fechas y validación posterior independiente.
            </p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[480px] text-left text-xs">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2">Bloque</th>
                    <th>Retorno 12 meses</th>
                    <th>SPY</th>
                    <th>Cobertura</th>
                  </tr>
                </thead>
                <tbody>
                  {data.blocks.map((row) => (
                    <tr key={row.block} className="border-b last:border-0">
                      <td className="py-2">{row.block}</td>
                      {row.outcome.status === 'reserved' ? (
                        <td colSpan={3}>reservado (acaba el {row.outcome.end_date})</td>
                      ) : (
                        <>
                          <td>{signedPct(row.outcome.portfolio_return)}</td>
                          <td>{signedPct(row.outcome.benchmark_return)}</td>
                          <td>
                            {row.outcome.available ?? 0}/
                            {row.outcome.requested ?? row.symbols.length}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="break-all text-xs text-muted-foreground">
            Coste {data.cost_bps} pb · corte observado {data.observed_cutoff} · SHA-256{' '}
            {data.result_sha256}
          </p>
        </div>
      )}
    </section>
  );
}
