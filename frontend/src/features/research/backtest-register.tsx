import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { createJob, getJob, getJobResult } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState } from '@/shared/ui/resource-state';

type Stage = 'RESEARCH' | 'IN_SAMPLE' | 'OUT_OF_SAMPLE' | 'LIVE_FORWARD';

const STAGES: { value: Stage; label: string }[] = [
  { value: 'RESEARCH', label: 'Research (explorando configuraciones)' },
  { value: 'IN_SAMPLE', label: 'In-sample (rango usado para diseñar)' },
  { value: 'OUT_OF_SAMPLE', label: 'Out-of-sample (datos no mirados al diseñar)' },
  { value: 'LIVE_FORWARD', label: 'Live forward (seguimiento real)' },
];

function experimentId(result: unknown): number | null {
  if (typeof result !== 'object' || result == null || !('experiment_id' in result)) return null;
  return typeof result.experiment_id === 'number' ? result.experiment_id : null;
}

export function BacktestRegister({ sourceJobId }: { sourceJobId: string }) {
  const [stage, setStage] = useState<Stage>('RESEARCH');
  const [family, setFamily] = useState('');
  const [hypothesis, setHypothesis] = useState(false);
  const [notes, setNotes] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const register = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'backtest_register',
        research_log: {
          source_job_id: sourceJobId,
          stage,
          hypothesis_registered: hypothesis,
          family: family.trim() || null,
          notes: notes.trim() || null,
        },
        idempotency_key: 'register:' + sourceJobId,
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
    queryKey: ['job-result', jobId],
    queryFn: ({ signal }) => getJobResult(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const registered = experimentId(result.data);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    register.mutate();
  }

  return (
    <details className="rounded-lg border p-4 text-sm">
      <summary className="cursor-pointer font-medium">
        Registrar este experimento en Research Lab
      </summary>
      <p className="mt-2 text-xs text-muted-foreground">
        Guarda los parámetros, métricas y la serie de retornos del artefacto verificado, con su hash
        y la huella de los datos locales. La huella recorre todas las tablas de la base y puede
        tardar más de diez minutos; se calcula al registrar, no al terminar el backtest. Cada
        backtest solo se puede registrar una vez, para no inflar el recuento de ensayos.
      </p>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-medium">
          Fase
          <select
            className="mt-1.5 block h-10 w-full rounded-md border bg-background px-2 text-sm"
            value={stage}
            onChange={(event) => setStage(event.target.value as Stage)}
          >
            {STAGES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium">
          Familia (agrupa intentos comparables)
          <Input
            className="mt-1.5"
            maxLength={100}
            value={family}
            onChange={(event) => setFamily(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-xs font-medium sm:col-span-2">
          <input
            type="checkbox"
            checked={hypothesis}
            onChange={(event) => setHypothesis(event.target.checked)}
          />
          Hipótesis registrada formalmente antes de ver el resultado
        </label>
        <label className="text-xs font-medium sm:col-span-2">
          Notas
          <textarea
            className="mt-1.5 block min-h-20 w-full rounded-md border bg-background p-2 text-sm"
            maxLength={2000}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </label>
        <Button className="w-fit" type="submit" disabled={register.isPending || jobId != null}>
          Registrar en Research Lab
        </Button>
      </form>
      {register.isError && <ErrorState error={register.error} retry={() => register.mutate()} />}
      {job.data && registered == null && (
        <p className="mt-3 text-muted-foreground">
          Registro #{job.data.id.slice(0, 8)} · {job.data.phase} · {job.data.status}
        </p>
      )}
      {job.data?.status === 'failed' && (
        <p className="mt-2 text-destructive">
          No se registró. Puede que este backtest ya estuviera registrado o que su artefacto no se
          pueda verificar.
        </p>
      )}
      {registered != null && (
        <p className="mt-3 font-medium">Experimento #{registered} registrado en Research Lab.</p>
      )}
    </details>
  );
}
