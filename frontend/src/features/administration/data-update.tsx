import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { createJob, getJob, getJobResult } from '@/shared/api/client';
import type { DataUpdateRequest } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';

type UpdateResult = {
  symbols: number;
  retry: boolean;
  price_refreshed: boolean;
  fundamentals_refreshed: number;
  edgar_refreshed: number;
  failed_symbols: string[];
  failure_groups: { reason: string; symbols: string[] }[];
};

/** The old «Actualizar datos»: universe size, forced download, failures by reason and retry. */
export function DataUpdate() {
  const [limit, setLimit] = useState<'50' | '150' | 'all'>('50');
  const [force, setForce] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: (update: DataUpdateRequest) =>
      createJob({ kind: 'data_update', update, idempotency_key: 'update:' + crypto.randomUUID() }),
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
    queryKey: ['job', jobId, 'result'],
    queryFn: ({ signal }) => getJobResult(jobId!, signal) as Promise<UpdateResult>,
    enabled: job.data?.status === 'succeeded',
  });
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  const data = result.data;
  return (
    <section className="space-y-3 rounded-lg border p-4 text-sm" aria-label="Actualizar datos">
      <p className="font-medium">Actualizar datos</p>
      <p className="text-xs text-muted-foreground">
        Precios y fundamentales de Yahoo Finance y datos oficiales de SEC EDGAR, descargando solo lo
        caducado. Empieza con un subconjunto pequeño: la primera descarga de fundamentales tarda.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1">
          Tamaño del universo
          <NativeSelect
            value={limit}
            onChange={(event) => setLimit(event.target.value as '50' | '150' | 'all')}
          >
            <NativeSelectOption value="50">Prueba rápida (50 empresas)</NativeSelectOption>
            <NativeSelectOption value="150">Medio (150 empresas)</NativeSelectOption>
            <NativeSelectOption value="all">Completo (S&amp;P 500)</NativeSelectOption>
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={force}
            onChange={(event) => setForce(event.target.checked)}
          />
          Forzar descarga aunque los datos estén frescos
        </label>
        <Button
          disabled={running}
          onClick={() =>
            start.mutate({
              universe_limit: limit === 'all' ? null : (Number(limit) as 50 | 150),
              force,
            })
          }
        >
          Actualizar datos
        </Button>
      </div>
      {start.isError && <p className="text-destructive">{start.error.message}</p>}
      {job.data && job.data.status !== 'succeeded' && (
        <p role="status" className="text-muted-foreground">
          {job.data.phase} · {job.data.progress} % · {job.data.status}
        </p>
      )}
      {data && (
        <div className="space-y-2" role="region" aria-label="Resultado de la actualización">
          <p>
            {data.retry ? 'Reintento' : 'Actualización'} de {data.symbols} empresas · precios
            refrescados: {data.price_refreshed ? 'sí' : 'no (ya estaban al día)'} · fundamentales
            Yahoo actualizados: {data.fundamentals_refreshed} · datos SEC EDGAR actualizados:{' '}
            {data.edgar_refreshed} · empresas con fallos: {data.failed_symbols.length}
          </p>
          {data.failure_groups.length === 0 ? (
            <p>Ninguna empresa ha fallado en esta actualización.</p>
          ) : (
            <>
              <ul className="space-y-1">
                {data.failure_groups.map((group) => (
                  <li key={group.reason}>
                    <details>
                      <summary className="cursor-pointer">
                        {group.reason} — {group.symbols.length} empresas
                      </summary>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {group.symbols.join(', ')}
                      </p>
                    </details>
                  </li>
                ))}
              </ul>
              {data.failure_groups.some((group) =>
                group.reason.toLowerCase().includes('límite de peticiones'),
              ) && (
                <p className="text-xs text-muted-foreground">
                  Si muchos fallos son por límite de peticiones, Yahoo Finance te está limitando
                  temporalmente: espera unos minutos y reintenta solo los fallidos.
                </p>
              )}
              <Button
                variant="outline"
                disabled={running}
                onClick={() => start.mutate({ symbols: data.failed_symbols, force: true })}
              >
                Reintentar solo los fallidos
              </Button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
