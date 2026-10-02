import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  cancelJob,
  createJob,
  getEstimateAnalysisPreview,
  getEstimateCaptures,
  getJob,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatNumber } from '@/shared/lib/format';
import { ResearchModeNotice } from '@/shared/ui/research-mode';

export function EstimateCaptures({ researchAllowed }: { researchAllowed: boolean }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ['research', 'estimate-captures'],
    queryFn: ({ signal }) => getEstimateCaptures(signal),
  });
  const start = useMutation({
    mutationFn: () =>
      createJob({ kind: 'estimate_analysis', idempotency_key: 'estimates:' + crypto.randomUUID() }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (result) =>
      ['queued', 'running'].includes(result.state.data?.status ?? '') ? 2000 : false,
  });
  const preview = useQuery({
    queryKey: ['research', 'estimate-analysis', jobId],
    queryFn: ({ signal }) => getEstimateAnalysisPreview(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  if (!data) return null;
  return (
    <section className="rounded-xl border bg-card p-5" aria-labelledby="estimate-captures-heading">
      <h2 id="estimate-captures-heading" className="text-xl font-semibold">
        Estimaciones de consenso
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Archivo experimental de capturas reales del consenso. Yahoo no ofrece el historial de
        estimaciones de fechas pasadas; GABI solo puede estudiar las fotos guardadas desde cada
        sincronización. Esta consulta no calcula retornos ni Rank IC.
      </p>
      <p className="mt-3 text-sm">
        {data.batches_eligible} de {data.batches_total} capturas tienen al menos{' '}
        {data.symbols_per_batch_needed} empresas. Se necesitan {data.batches_needed} capturas
        separadas por {data.span_days_needed} días; el margen actual es de {data.span_days} días.
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        {data.history_threshold_met
          ? 'Hay profundidad suficiente para plantear un experimento explícito, sujeto al corte observado y al registro previo.'
          : 'Aún falta profundidad para plantear el experimento.'}{' '}
        Ninguna ventaja frente al S&amp;P 500 queda demostrada por estas capturas.
      </p>
      <Button
        className="mt-4"
        type="button"
        disabled={!researchAllowed || start.isPending}
        onClick={() => {
          setJobId(null);
          start.mutate();
        }}
      >
        Evaluar revisiones hasta julio de 2025
      </Button>
      {!researchAllowed && (
        <ResearchModeNotice action="El análisis de estimaciones" className="mt-2" />
      )}
      {start.isError && <ErrorState error={start.error} retry={() => start.mutate()} />}
      {job.isError && <ErrorState error={job.error} retry={() => void job.refetch()} />}
      {job.data && (
        <p className="mt-3 text-sm text-muted-foreground">
          Trabajo {job.data.id.slice(0, 8)} · {job.data.phase} · {job.data.progress} % ·{' '}
          {job.data.status}
        </p>
      )}
      {job.data && ['queued', 'running'].includes(job.data.status) && (
        <Button
          className="mt-2"
          type="button"
          variant="outline"
          disabled={cancel.isPending}
          onClick={() => cancel.mutate()}
        >
          Solicitar cancelación
        </Button>
      )}
      {job.data?.status === 'failed' && (
        <p className="mt-2 text-sm text-destructive">No se pudo completar el análisis local.</p>
      )}
      {preview.isPending && job.data?.status === 'succeeded' && <LoadingState />}
      {preview.isError && <ErrorState error={preview.error} retry={() => void preview.refetch()} />}
      {preview.data && (
        <div className="mt-4 space-y-3">
          <p className="text-sm">
            {preview.data.status === 'insufficient_data'
              ? preview.data.reason
              : `Rank IC retrospectivo calculado con ${preview.data.batches_available} capturas observadas.`}
          </p>
          {preview.data.summary.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b">
                    <th>Horizonte</th>
                    <th>IC medio</th>
                    <th>Periodos</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.data.summary.map((row) => (
                    <tr className="border-b" key={row.horizonte}>
                      <td>{row.horizonte} meses</td>
                      <td>{formatNumber(row.ic_mean, { digits: 3, fixed: true })}</td>
                      <td>{row.n_periods}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <a
            className="text-sm text-primary underline"
            href={`/api/v1/jobs/${preview.data.job_id}/result`}
            download={`gabi-estimaciones-${preview.data.job_id}.json`}
          >
            Descargar serie y resumen íntegros
          </a>
          <p className="break-all text-xs text-muted-foreground">
            SHA-256: {preview.data.result_sha256}
          </p>
        </div>
      )}
    </section>
  );
}
