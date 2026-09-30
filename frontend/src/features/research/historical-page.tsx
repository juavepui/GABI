import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { cancelJob, createJob, getHistoricalPreview, getJob, getModel } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { BacktestPanel } from './backtest-panel';

const number = (value: number | null | undefined) =>
  value == null ? '—' : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(value);

export function HistoricalPage() {
  const model = useQuery({ queryKey: ['model'], queryFn: ({ signal }) => getModel(signal) });
  const [asOf, setAsOf] = useState('2019-01-02');
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'historical_ranking',
        start: asOf,
        idempotency_key: 'historical:' + crypto.randomUUID(),
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
  const preview = useQuery({
    queryKey: ['research', 'historical', jobId],
    queryFn: ({ signal }) => getHistoricalPreview(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJobId(null);
    start.mutate();
  }

  return (
    <div className="space-y-6">
      <header>
        <Link className="text-sm text-primary" to="/investigacion">
          ← Investigación
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Ranking histórico</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Reconstruye el S&amp;P 500 en una fecha ya observada. El cálculo usa el motor histórico
          existente y se ejecuta en el worker; no crea una validación independiente ni consulta las
          reservas prospectivas o anteriores a 2010.
        </p>
      </header>
      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-5"
      >
        <label className="text-xs font-medium">
          Fecha de referencia
          <Input
            className="mt-1.5"
            type="date"
            value={asOf}
            min="2010-01-01"
            max="2025-07-02"
            onChange={(event) => setAsOf(event.target.value)}
            required
          />
        </label>
        <Button disabled={start.isPending} type="submit">
          Calcular ranking
        </Button>
      </form>
      {start.isError && <ErrorState error={start.error} retry={() => start.mutate()} />}
      {job.isError && <ErrorState error={job.error} retry={() => void job.refetch()} />}
      {job.data && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="font-semibold">Trabajo #{job.data.id.slice(0, 8)}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {job.data.phase} · {job.data.progress} % · {job.data.status}
          </p>
          {['queued', 'running'].includes(job.data.status) && (
            <Button
              className="mt-3"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Solicitar cancelación
            </Button>
          )}
          {job.data.status === 'failed' && (
            <p className="mt-3 text-sm text-destructive">
              El cálculo no terminó. Revisa cobertura y datos locales.
            </p>
          )}
        </section>
      )}
      {preview.isPending && job.data?.status === 'succeeded' && <LoadingState />}
      {preview.isError && <ErrorState error={preview.error} retry={() => void preview.refetch()} />}
      {preview.data && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="text-xl font-semibold">Ranking a {preview.data.as_of}</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {preview.data.total} empresas · se muestran las primeras {preview.data.shown} en el
            orden original. Identidad y sector aproximados permanecen visibles; el JSON completo se
            conserva con hash {preview.data.result_sha256.slice(0, 12)}…
          </p>
          <a
            className="mt-3 inline-block text-sm text-primary underline"
            href={'/api/v1/jobs/' + preview.data.job_id + '/result'}
            download={'gabi-ranking-' + preview.data.as_of + '.json'}
          >
            Descargar resultado completo
          </a>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="py-2">Empresa</th>
                  <th>Sector</th>
                  <th>Score</th>
                  <th>Cobertura</th>
                  <th>Identidad</th>
                  <th>Precio</th>
                </tr>
              </thead>
              <tbody>
                {preview.data.rows.map((row) => (
                  <tr key={row.symbol} className="border-b last:border-0">
                    <td className="py-3">
                      <span className="font-medium">{row.symbol}</span>
                      <span className="block text-xs text-muted-foreground">{row.name ?? '—'}</span>
                    </td>
                    <td>
                      {row.sector ?? '—'}
                      {row.sector_is_approximate && ' · aproximado'}
                    </td>
                    <td>{number(row.composite_score)}</td>
                    <td>
                      {row.score_coverage == null ? '—' : number(row.score_coverage * 100) + ' %'}
                    </td>
                    <td>{row.identity_status ?? '—'}</td>
                    <td>{number(row.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <BacktestPanel researchAllowed={model.data?.mode === 'RESEARCH'} />
    </div>
  );
}
