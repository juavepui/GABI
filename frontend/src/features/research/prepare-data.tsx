import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { cancelJob, createJob, getJob, getPreparation } from '@/shared/api/client';
import type { PreparationRequest } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

export function PrepareData({
  label,
  start,
  end,
  preparation,
}: {
  label: string;
  start: string;
  end: string | null;
  preparation: PreparationRequest;
}) {
  const [jobId, setJobId] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'prepare_history',
        start,
        end,
        preparation,
        idempotency_key: 'prepare:' + crypto.randomUUID(),
      }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 3000 : false,
  });
  const result = useQuery({
    queryKey: ['research', 'preparation', jobId],
    queryFn: ({ signal }) => getPreparation(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });
  const data = result.data;

  return (
    <div className="space-y-2 text-sm">
      <Button
        type="button"
        variant="outline"
        disabled={run.isPending || ['queued', 'running'].includes(job.data?.status ?? '')}
        onClick={() => {
          setJobId(null);
          run.mutate();
        }}
      >
        {label}
      </Button>
      <p className="text-xs text-muted-foreground">
        Descarga SEC EDGAR y precios históricos de las empresas que falten. Es la única acción de
        esta página que usa la red y escribe en la base local; con rangos largos puede tardar varios
        minutos.
      </p>
      {run.isError && <ErrorState error={run.error} retry={() => run.mutate()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <p className="text-muted-foreground">
          Preparación #{job.data.id.slice(0, 8)} · {job.data.phase} · {job.data.status}
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
        <p className="text-destructive">
          La preparación no terminó. Revisa la conexión y reinténtalo.
        </p>
      )}
      {result.isPending && job.data?.status === 'succeeded' && <LoadingState />}
      {result.isError && <ErrorState error={result.error} retry={() => void result.refetch()} />}
      {data && (
        <div
          className="rounded-lg border p-3"
          aria-label="Resultado de la preparación"
          role="region"
        >
          <p className="font-medium">
            Preparación terminada · {data.symbols} símbolos
            {data.scope === 'backtest' ? ' históricos y SPY' : ''}
          </p>
          {data.universe_note && (
            <p className="text-xs text-muted-foreground">
              {data.universe_is_exact ? '✅' : '⚠️'} {data.universe_note}
            </p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {data.scope === 'date'
              ? `SEC EDGAR actualizado: ${data.edgar_refreshed} · precios ampliados: ${data.prices_deep_fetched} (ya cubrían la fecha: ${data.prices_already_covered}) · `
              : ''}
            símbolos con algún fallo: {data.failed_symbols}
          </p>
          {data.failures.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs">
                Ver los {data.failed_symbols} símbolos con algún fallo
              </summary>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {data.failures.map((row) => (
                  <li key={row.symbol + row.etapa}>
                    {row.symbol} · {row.etapa} · {row.motivo}
                  </li>
                ))}
              </ul>
              {data.failures_truncated && (
                <p className="mt-1 text-xs">Lista recortada a los primeros 1.000 fallos.</p>
              )}
            </details>
          )}
        </div>
      )}
    </div>
  );
}
