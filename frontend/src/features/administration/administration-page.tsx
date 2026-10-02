import { useState } from 'react';
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

const sourceNames: Record<string, string> = {
  prices: 'Precios',
  fundamentals: 'Fundamentales',
  edgar_metrics: 'SEC EDGAR',
};

function JobRow({
  job,
  onCancel,
  onResult,
}: {
  job: JobResponse;
  onCancel: (id: string) => void;
  onResult: (id: string) => void;
}) {
  const [activity, setActivity] = useState(false);
  const detail = useQuery({
    queryKey: ['job', job.id],
    queryFn: ({ signal }) => getJob(job.id, signal),
    enabled: activity,
    refetchInterval: activity && job.status === 'running' ? 3000 : false,
  });
  return (
    <li className="rounded-lg border p-4" aria-label={jobName(job.kind)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium">{jobName(job.kind)}</p>
          <p className="text-xs text-muted-foreground">
            {new Date(job.created_at).toLocaleString('es-ES')} ·{' '}
            {job.origin === 'scheduler' ? 'Programador' : 'Manual'}
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
        <p className="mt-3 text-sm text-muted-foreground">{job.phase}</p>
      )}
      {job.status === 'failed' && (
        <p className="mt-2 text-sm text-destructive">
          El trabajo falló. Revisa las fuentes locales antes de repetirlo.
        </p>
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
  async function showResult(id: string) {
    try {
      setResult(await getJobResult(id));
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se puede abrir el resultado.');
    }
  }
  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
          Operación local
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Administración</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Solicita actualizaciones y auditorías. El worker continúa aunque cierres el navegador.
        </p>
        <SectionLinks
          label="Apartados de Administración"
          links={[
            {
              to: '/administracion/calidad',
              label: 'Calidad de los datos',
              description: 'Cobertura, frescura, procedencia y archivo histórico',
              icon: ShieldCheck,
              tone: 'teal',
            },
          ]}
        />
      </div>
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
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => submit.mutate({ kind: 'refresh' })}
                disabled={submit.isPending}
              >
                Actualizar universo
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
                <input
                  id="symbols"
                  className="min-w-0 flex-1 rounded-md border bg-background px-3 py-2 text-sm"
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
                <WeightsEditor
                  key={`${model.data.mode}:${Object.values(model.data.weights).join(':')}`}
                  model={model.data}
                />
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>
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
              <input
                type="date"
                min="2010-01-01"
                max="2025-07-02"
                value={start}
                onChange={(event) => setStart(event.target.value)}
                className="mt-1 block rounded-md border bg-background p-2"
                required
              />
            </label>
            <label className="text-sm">
              Hasta
              <input
                type="date"
                min="2010-01-01"
                max="2025-07-02"
                value={end}
                onChange={(event) => setEnd(event.target.value)}
                className="mt-1 block rounded-md border bg-background p-2"
                required
              />
            </label>
            <Button type="submit" disabled={submit.isPending}>
              Iniciar backtest
            </Button>
          </form>
        </CardContent>
      </Card>
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
          {jobs.isLoading ? (
            <p className="text-sm text-muted-foreground">Cargando trabajos…</p>
          ) : jobs.isError ? (
            <p role="alert" className="text-sm text-destructive">
              No se pueden consultar los trabajos.
            </p>
          ) : jobs.data?.jobs.length ? (
            <ul className="space-y-3">
              {jobs.data.jobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  onCancel={(id) => cancel.mutate(id)}
                  onResult={(id) => void showResult(id)}
                />
              ))}
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
