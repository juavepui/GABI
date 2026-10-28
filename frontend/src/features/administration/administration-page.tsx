import { useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, DatabaseZap, RefreshCw, ShieldCheck } from 'lucide-react';
import {
  cancelJob,
  createJob,
  getJob,
  getJobResult,
  getJobs,
  getLocalSettings,
  getModel,
  retryJob,
} from '@/shared/api/client';
import type { CreateJobRequest, JobResponse } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card';
import { WeightsEditor } from './weights-editor';
import { ModeSelector } from './mode-selector';
import { DataUpdate } from './data-update';
import { KeyEditor } from './key-editor';
import { SectionLinks } from '@/shared/ui/section-links';
import { ProgressBar } from '@/shared/ui/progress-bar';
import { JOB_STATES, jobName } from '@/shared/lib/jobs';
import { PageHeader } from '@/shared/ui/page-header';
import { Input } from '@/shared/ui/input';

const sourceNames: Record<string, string> = {
  prices: 'Precios',
  fundamentals: 'Fundamentales',
  edgar_metrics: 'SEC EDGAR',
};

const failureSources: Record<string, string> = {
  yahoo: 'Yahoo',
  sec: 'SEC EDGAR',
  universe: 'Universo',
  fred: 'FRED',
};

function SourceFailures({
  failures,
  total,
}: {
  failures: NonNullable<JobResponse['failures']>;
  total: number;
}) {
  return (
    <ul className="mt-2 flex flex-wrap gap-2 text-xs" aria-label="Fuentes fallidas">
      {failures.map((failure) => (
        <li
          key={`${failure.source}-${failure.symbol}`}
          className="rounded-md border border-destructive/40 px-2 py-1"
        >
          {failureSources[failure.source] ?? failure.source} · {failure.symbol}
        </li>
      ))}
      {total > failures.length && (
        <li className="px-2 py-1 text-muted-foreground">y {total - failures.length} más</li>
      )}
    </ul>
  );
}

const RECENT_JOBS = 5;

/** The latest jobs, plus any still running or just retried, so the actions stay above the history. */
function visibleJobs(jobs: JobResponse[], all: boolean, retried: string | null): JobResponse[] {
  if (all) return jobs;
  return jobs.filter(
    (job, index) =>
      index < RECENT_JOBS || ['queued', 'running'].includes(job.status) || job.id === retried,
  );
}

function JobRow({
  job,
  onCancel,
  onResult,
  onRetry,
  retryPending,
}: {
  job: JobResponse;
  onCancel: (id: string) => void;
  onResult: (id: string) => void;
  onRetry: (id: string) => void;
  retryPending: boolean;
}) {
  const [activity, setActivity] = useState(false);
  const detail = useQuery({
    queryKey: ['job', job.id],
    queryFn: ({ signal }) => getJob(job.id, signal),
    enabled: activity,
    refetchInterval: activity && job.status === 'running' ? 3000 : false,
  });
  return (
    <li
      id={'job-' + job.id}
      className="scroll-mt-4 rounded-lg border p-4"
      aria-label={jobName(job.kind)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium">{jobName(job.kind)}</p>
          <p className="text-xs text-muted-foreground">
            {new Date(job.created_at).toLocaleString('es-ES')} ·{' '}
            {job.origin === 'scheduler' ? 'Programador' : 'Manual'}
            {' · #'}
            {job.id.slice(0, 8)}
          </p>
        </div>
        <span className="rounded-full bg-muted px-2 py-1 text-xs font-medium">
          {JOB_STATES[job.status] ?? job.status}
        </span>
      </div>
      {['queued', 'running'].includes(job.status) ? (
        <div className="mt-3">
          <ProgressBar value={job.progress} phase={job.phase} status={job.status} />
        </div>
      ) : (
        job.phase !== JOB_STATES[job.status] && (
          <p className="mt-3 text-sm text-muted-foreground">{job.phase}</p>
        )
      )}
      {job.status === 'failed' && job.failure && (
        <div className="mt-2 space-y-1 text-sm" aria-label="Causa del fallo">
          <p className="font-medium text-destructive">{job.failure.label}</p>
          <p>{job.failure.message} No se publicó un resultado.</p>
          {job.last_activity && (
            <p className="text-xs text-muted-foreground">
              Último paso antes del fallo: {job.last_activity}
            </p>
          )}
          <p>
            <span className="font-medium">Qué hacer: </span>
            {job.failure.action}
          </p>
          {job.diagnostic && (
            <p className="text-xs text-muted-foreground">
              Traza local en la carpeta de datos: jobs/logs/{job.id}.log
            </p>
          )}
        </div>
      )}
      {job.status === 'cancelled' && (
        <p className="mt-2 text-sm text-muted-foreground">
          Cancelación completada. No se publicó un resultado.
        </p>
      )}
      {job.status === 'running' && job.cancel_requested && (
        <p className="mt-2 text-sm text-muted-foreground">
          La cancelación está solicitada. El trabajo sigue en curso hasta alcanzar un punto seguro.
        </p>
      )}
      {job.status === 'failed' && job.failures && job.failures.length > 0 && (
        <SourceFailures failures={job.failures} total={job.failures_total ?? job.failures.length} />
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" variant="ghost" onClick={() => setActivity(!activity)}>
          {activity ? 'Ocultar actividad' : 'Ver actividad'}
        </Button>
        {(job.status === 'queued' || job.status === 'running') && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onCancel(job.id)}
            disabled={job.cancel_requested}
          >
            {job.cancel_requested ? 'Cancelación solicitada' : 'Cancelar'}
          </Button>
        )}
        {['failed', 'cancelled'].includes(job.status) &&
          ['refresh', 'quality'].includes(job.kind) && (
            <Button
              size="sm"
              variant="outline"
              disabled={retryPending}
              onClick={() => onRetry(job.id)}
              title={
                job.failure?.retry === 'no'
                  ? 'Un error interno probablemente se repetirá'
                  : job.failure?.retry === 'after_fix'
                    ? 'Corrige antes la causa indicada'
                    : undefined
              }
            >
              Solicitar nuevo intento
            </Button>
          )}
        {job.status === 'succeeded' &&
          job.result_ref &&
          !['maintenance', 'tiingo'].includes(job.kind) && (
            <Button size="sm" variant="outline" onClick={() => onResult(job.id)}>
              Ver resultado
            </Button>
          )}
      </div>
      {activity && (
        <div className="mt-3 rounded-md bg-muted p-3 text-xs">
          {detail.isLoading ? (
            'Cargando actividad…'
          ) : detail.isError ? (
            'No se puede consultar la actividad.'
          ) : (
            <ol className="space-y-1">
              {detail.data?.events?.map((event, index) => (
                <li key={`${event.at}-${index}`}>
                  {new Date(event.at).toLocaleString('es-ES')} · {event.message}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}

function qualityRows(value: unknown): { name: string; covered: number; total: number }[] | null {
  if (!value || typeof value !== 'object' || !('sources' in value)) return null;
  const sources = value.sources;
  if (!sources || typeof sources !== 'object') return null;
  const rows = Object.entries(sources).map(([name, entry]) => {
    if (
      !entry ||
      typeof entry !== 'object' ||
      !('covered' in entry) ||
      !('total' in entry) ||
      typeof entry.covered !== 'number' ||
      typeof entry.total !== 'number'
    )
      return null;
    return { name, covered: entry.covered, total: entry.total };
  });
  return rows.every((row) => row !== null)
    ? (rows as { name: string; covered: number; total: number }[])
    : null;
}

export function AdministrationPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [showAllJobs, setShowAllJobs] = useState(false);
  const retryInFlight = useRef(false);
  const retryKeys = useRef(new Map<string, string>());
  const [symbols, setSymbols] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState('');
  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: ({ signal }) => getJobs(signal),
    refetchInterval: 3000,
  });
  const settings = useQuery({
    queryKey: ['local-settings'],
    queryFn: ({ signal }) => getLocalSettings(signal),
  });
  const model = useQuery({
    queryKey: ['model'],
    queryFn: ({ signal }) => getModel(signal),
    refetchInterval: 10_000,
  });
  const submit = useMutation({
    mutationFn: (request: Omit<CreateJobRequest, 'idempotency_key'>) =>
      createJob({ ...request, idempotency_key: crypto.randomUUID() }),
    onSuccess: () => {
      setError('');
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
    onError: (cause: Error) => setError(cause.message),
  });
  const cancel = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      setError('');
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
    onError: (cause: Error) => setError(cause.message),
  });
  const repeat = useMutation({
    mutationFn: ({ id, key }: { id: string; key: string }) => retryJob(id, key),
    onSuccess: (job, { id }) => {
      setError('');
      setResult(null);
      retryKeys.current.delete(id);
      try {
        sessionStorage.removeItem('gabi-job-retry:' + id);
      } catch {
        /* Optional persistence. */
      }
      setParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set('retry_job', job.id);
        return next;
      });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
    onError: (cause: Error) => setError(cause.message),
    onSettled: () => {
      retryInFlight.current = false;
    },
  });
  function repeatJob(id: string) {
    if (retryInFlight.current) return;
    retryInFlight.current = true;
    let key = retryKeys.current.get(id);
    try {
      key ??= sessionStorage.getItem('gabi-job-retry:' + id) ?? undefined;
    } catch {
      /* Optional persistence. */
    }
    key ??= crypto.randomUUID();
    retryKeys.current.set(id, key);
    try {
      sessionStorage.setItem('gabi-job-retry:' + id, key);
    } catch {
      /* Keep in memory. */
    }
    repeat.mutate({ id, key });
  }
  const retriedJob = params.get('retry_job');
  async function showResult(id: string) {
    setResult(null);
    try {
      setResult(await getJobResult(id));
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se puede abrir el resultado.');
    }
  }
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Operación local"
        title="Administración"
        description="Solicita actualizaciones y auditorías. El worker continúa aunque cierres el navegador."
      >
        <SectionLinks
          label="Apartados de Administración"
          links={[
            {
              to: '/administracion/calidad',
              label: 'Calidad de los datos',
              description: 'Cobertura, frescura, procedencia y archivo histórico',
              icon: ShieldCheck,
            },
          ]}
        />
      </PageHeader>
      {error && (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-destructive/30 p-3 text-sm text-destructive"
        >
          <AlertCircle size={16} />
          {error}
        </p>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <DatabaseZap size={19} />
              Datos
            </CardTitle>
            <CardDescription>Las consultas a esta página no descargan datos.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <DataUpdate />
            <p className="text-xs text-muted-foreground">
              «Actualización completa» revisa la composición del S&amp;P 500 y actualiza precios,
              fundamentales y SEC de todo el universo y de los índices de referencia, además de las
              series macro de FRED. Es la que el Programador lanza cada día.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => submit.mutate({ kind: 'refresh' })}
                disabled={submit.isPending}
              >
                Actualización completa
              </Button>
              <Button
                variant="outline"
                onClick={() => submit.mutate({ kind: 'quality' })}
                disabled={submit.isPending}
              >
                Auditar cobertura
              </Button>
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                const items = symbols
                  .toUpperCase()
                  .split(/[\s,;]+/)
                  .filter(Boolean);
                submit.mutate({ kind: 'symbols', symbols: items });
              }}
              className="space-y-2"
            >
              <label htmlFor="symbols" className="block text-sm font-medium">
                Descargar símbolos concretos
              </label>
              <div className="flex gap-2">
                <Input
                  id="symbols"
                  className="flex-1"
                  value={symbols}
                  onChange={(event) => setSymbols(event.target.value)}
                  placeholder="SPY, RSP"
                />
                <Button type="submit" variant="outline" disabled={submit.isPending}>
                  Solicitar
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Hasta diez símbolos. Usa la caché incremental y los límites de las fuentes.
              </p>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck size={19} />
              Configuración local
            </CardTitle>
            <CardDescription>
              Solo se indica si existe una clave; nunca se muestran valores o rutas. Guardar una
              clave la escribe en un fichero local.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {settings.isLoading ? (
              <p className="text-sm text-muted-foreground">Comprobando configuración…</p>
            ) : settings.isError ? (
              <p role="alert" className="text-sm text-destructive">
                No se puede consultar la configuración.
              </p>
            ) : (
              <KeyEditor keys={settings.data?.keys ?? {}} />
            )}
            {model.isLoading ? (
              <p className="mt-4 text-sm text-muted-foreground">Leyendo modelo…</p>
            ) : model.isError ? (
              <p role="alert" className="mt-4 text-sm text-destructive">
                No se puede leer el modelo.
              </p>
            ) : model.data ? (
              <>
                <ModeSelector model={model.data} />
                {/* Investor uses the frozen weights: nothing to edit or compare. */}
                {model.data.mode === 'RESEARCH' && (
                  <WeightsEditor
                    key={`${model.data.mode}:${Object.values(model.data.weights).join(':')}`}
                    model={model.data}
                  />
                )}
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>
      {model.data?.mode === 'RESEARCH' && (
        <Card>
          <CardHeader>
            <CardTitle>Investigación exploratoria</CardTitle>
            <CardDescription>
              Backtest histórico de hasta un año entre 2010 y julio de 2025. El resultado se guarda
              como artefacto verificable; no constituye validación prospectiva.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                submit.mutate({ kind: 'backtest', start, end });
              }}
              className="flex flex-wrap items-end gap-3"
            >
              <label className="text-sm">
                Desde
                <Input
                  type="date"
                  min="2010-01-01"
                  max="2025-07-02"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  className="mt-1 w-auto"
                  required
                />
              </label>
              <label className="text-sm">
                Hasta
                <Input
                  type="date"
                  min="2010-01-01"
                  max="2025-07-02"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  className="mt-1 w-auto"
                  required
                />
              </label>
              <Button type="submit" disabled={submit.isPending}>
                Iniciar backtest
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw size={19} />
            Trabajos
          </CardTitle>
          <CardDescription>
            Estado persistente compartido con el programador. Se actualiza cada tres segundos.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {retriedJob && /^[a-f0-9]{32}$/.test(retriedJob) && (
            <p role="status" className="mb-4 text-sm">
              Se ha solicitado un nuevo trabajo; el anterior conserva su estado.{' '}
              <a className="font-medium text-primary underline" href={'#job-' + retriedJob}>
                Ver nuevo intento #{retriedJob.slice(0, 8)}
              </a>
            </p>
          )}
          {jobs.isLoading ? (
            <p className="text-sm text-muted-foreground">Cargando trabajos…</p>
          ) : jobs.isError ? (
            <p role="alert" className="text-sm text-destructive">
              No se pueden consultar los trabajos.
            </p>
          ) : jobs.data?.jobs.length ? (
            <ul className="space-y-3">
              {visibleJobs(jobs.data.jobs, showAllJobs, retriedJob).map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  onCancel={(id) => cancel.mutate(id)}
                  onResult={(id) => void showResult(id)}
                  onRetry={repeatJob}
                  retryPending={repeat.isPending}
                />
              ))}
              {jobs.data.jobs.length > RECENT_JOBS && (
                <li>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-expanded={showAllJobs}
                    onClick={() => setShowAllJobs(!showAllJobs)}
                  >
                    {showAllJobs
                      ? 'Ver solo los últimos ' + RECENT_JOBS
                      : `Ver todos (${jobs.data.jobs.length})`}
                  </Button>
                </li>
              )}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              Aún no hay trabajos. Arranca el worker local para procesar las solicitudes.
            </p>
          )}
        </CardContent>
      </Card>
      {result !== null && (
        <Card>
          <CardHeader>
            <CardTitle>Resultado verificado</CardTitle>
          </CardHeader>
          <CardContent>
            {qualityRows(result) ? (
              <ul className="space-y-3" aria-label="Cobertura por fuente">
                {qualityRows(result)?.map((row) => (
                  <li key={row.name} className="rounded-md border p-3">
                    <div className="flex justify-between text-sm">
                      <span className="font-medium">{sourceNames[row.name] ?? row.name}</span>
                      <span>
                        {row.covered}/{row.total}
                      </span>
                    </div>
                    <div className="mt-2 h-2 rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{
                          width: `${row.total ? Math.min(100, (row.covered / row.total) * 100) : 0}%`,
                        }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-4 text-xs">
                {JSON.stringify(result, null, 2)}
              </pre>
            )}
            <Button className="mt-4" variant="outline" onClick={() => setResult(null)}>
              Cerrar resultado
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
