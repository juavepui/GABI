import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { cancelJob, createJob, getFactorPreview, getJob, getModel } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { PublishedFactorMap } from './published-factor-map';
import { EstimateCaptures } from './estimate-captures';
import { FactorGlossary, FactorQuantiles, SkippedPeriods } from './factor-details';
import { formatNumber } from '@/shared/lib/format';
import { PageHeader } from '@/shared/ui/page-header';

const format = (value: number | null | undefined, digits = 3) => formatNumber(value, { digits });

export function FactorPage() {
  const model = useQuery({ queryKey: ['model'], queryFn: ({ signal }) => getModel(signal) });
  const [start, setStart] = useState('2019-01-02');
  const [end, setEnd] = useState('2020-01-02');
  const [months, setMonths] = useState<1 | 3 | 6 | 12>(3);
  const [mode, setMode] = useState<'fast_dev' | 'validation'>('fast_dev');
  const [maxSymbols, setMaxSymbols] = useState<50 | 100 | 200>(50);
  const [jobId, setJobId] = useState<string | null>(null);
  const [neutral, setNeutral] = useState(false);
  const startJob = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'factor_analysis',
        start,
        end,
        factor_months: months,
        factor_mode: mode,
        factor_max_symbols: mode === 'fast_dev' ? maxSymbols : null,
        idempotency_key: 'factors:' + crypto.randomUUID(),
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
    queryKey: ['research', 'factors', jobId],
    queryFn: ({ signal }) => getFactorPreview(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });
  const summary = preview.data?.summary.filter((row) => row.sector_neutral === neutral) ?? [];

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJobId(null);
    startJob.mutate();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/investigacion', label: 'Investigación' }}
        title="Factor Lab"
        description={
          <>
            Estudia si cada score ordena los retornos futuros mediante Rank IC, quintiles y
            rotación. Son resultados retrospectivos exploratorios; no prueban una ventaja neta
            frente al S&amp;P 500.
          </>
        }
      />
      <FactorGlossary />
      <PublishedFactorMap />
      <EstimateCaptures researchAllowed={model.data?.mode === 'RESEARCH'} />
      {model.data?.mode === 'INVESTOR' && (
        <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
          Para ejecutar Factor Lab, activa el modo Research en{' '}
          <Link className="font-medium text-primary underline" to="/administracion">
            Administración
          </Link>
          . El servidor bloqueará el trabajo mientras esté activo el modo Investor.
        </p>
      )}
      <form
        onSubmit={submit}
        className="grid gap-4 rounded-xl border bg-card p-5 sm:grid-cols-2 lg:grid-cols-5"
      >
        <label className="text-xs font-medium">
          Inicio
          <Input
            className="mt-1.5"
            type="date"
            min="2010-01-01"
            max="2024-07-01"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            required
          />
        </label>
        <label className="text-xs font-medium">
          Fin
          <Input
            className="mt-1.5"
            type="date"
            min="2010-01-01"
            max="2024-07-01"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            required
          />
        </label>
        <label className="text-xs font-medium">
          Rebalanceo
          <select
            className="mt-1.5 block h-10 w-full rounded-md border bg-background px-2 text-sm"
            value={months}
            onChange={(event) => setMonths(Number(event.target.value) as 1 | 3 | 6 | 12)}
          >
            {[1, 3, 6, 12].map((value) => (
              <option key={value} value={value}>
                Cada {value} meses
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium">
          Modo
          <select
            className="mt-1.5 block h-10 w-full rounded-md border bg-background px-2 text-sm"
            value={mode}
            onChange={(event) => setMode(event.target.value as 'fast_dev' | 'validation')}
          >
            <option value="fast_dev">Muestra rápida</option>
            <option value="validation">Universo completo</option>
          </select>
        </label>
        {mode === 'fast_dev' && (
          <label className="text-xs font-medium">
            Empresas de muestra
            <select
              className="mt-1.5 block h-10 w-full rounded-md border bg-background px-2 text-sm"
              value={maxSymbols}
              onChange={(event) => setMaxSymbols(Number(event.target.value) as 50 | 100 | 200)}
            >
              {[50, 100, 200].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
        <p className="text-xs text-muted-foreground sm:col-span-2 lg:col-span-5">
          La muestra rápida sirve para iterar y no es evidencia citable. El universo completo puede
          tardar decenas de minutos. El último cierre permitido deja margen para los retornos
          futuros a 12 meses.
        </p>
        <Button
          className="w-fit sm:col-span-2"
          type="submit"
          disabled={startJob.isPending || model.data?.mode !== 'RESEARCH'}
        >
          Ejecutar Factor Lab
        </Button>
      </form>
      {startJob.isError && <ErrorState error={startJob.error} retry={() => startJob.mutate()} />}
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
              El análisis no terminó. Revisa la cobertura de datos locales.
            </p>
          )}
        </section>
      )}
      {preview.isPending && job.data?.status === 'succeeded' && <LoadingState />}
      {preview.isError && <ErrorState error={preview.error} retry={() => void preview.refetch()} />}
      {preview.data && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="text-xl font-semibold">Resumen de factores</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {preview.data.start} a {preview.data.end} ·{' '}
            {preview.data.mode === 'validation' ? 'Universo completo' : 'Muestra rápida'}
            {' · '}
            {preview.data.skipped_count} periodos saltados.
          </p>
          <SkippedPeriods skipped={preview.data.skipped} />
          <label className="mt-4 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={neutral}
              onChange={(event) => setNeutral(event.target.checked)}
            />
            Vista sector-neutral
          </label>
          {summary.length === 0 ? (
            <p className="mt-4 text-sm text-muted-foreground">
              Sin factores con cobertura suficiente.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[650px] text-left text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="py-2">Factor</th>
                    <th>Horizonte</th>
                    <th>IC medio</th>
                    <th>ICIR</th>
                    <th>Q máximo − Q1</th>
                    <th>Periodos</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.map((row) => (
                    <tr key={`${row.factor}-${row.horizonte}`} className="border-b last:border-0">
                      <td className="py-3">{row.factor}</td>
                      <td>{row.horizonte} meses</td>
                      <td>{format(row.ic_mean)}</td>
                      <td>{format(row.icir)}</td>
                      <td>{row.q_spread == null ? '—' : format(row.q_spread * 100, 2) + ' %'}</td>
                      <td>{row.n_periods}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <FactorQuantiles preview={preview.data} neutral={neutral} />
          {preview.data.turnover.length > 0 && (
            <div className="mt-7">
              <h3 className="font-semibold">Rotación media por quintil</h3>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[440px] text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="py-2">Factor</th>
                      <th>Quintil</th>
                      <th>Rotación</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.data.turnover.map((row) => (
                      <tr key={`${row.factor}-${row.quantil}`} className="border-b last:border-0">
                        <td className="py-2">{row.factor}</td>
                        <td>Q{row.quantil}</td>
                        <td>{row.turnover == null ? '—' : format(row.turnover * 100, 2) + ' %'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <a
            className="mt-4 inline-block text-sm text-primary underline"
            href={'/api/v1/jobs/' + preview.data.job_id + '/result'}
            download={'gabi-factor-lab-' + preview.data.job_id + '.json'}
          >
            Descargar series, quintiles, rotación y periodos saltados
          </a>
          <p className="mt-2 break-all text-xs text-muted-foreground">
            SHA-256: {preview.data.result_sha256}
          </p>
        </section>
      )}
    </div>
  );
}
