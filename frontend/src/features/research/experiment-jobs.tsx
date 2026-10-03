import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getExperimentBootstrap, getExperimentPbo, getExperiments } from '@/shared/api/client';
import type { ExperimentSummary } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { BlockBootstrapResult } from './block-bootstrap-view';
import { useJob } from '@/shared/api/use-job';
import { ProgressBar } from '@/shared/ui/progress-bar';
import { dateText, formatNumber, formatPercent } from '@/shared/lib/format';
import { Term } from '@/shared/ui/term';
import { HowToRead } from '@/shared/ui/how-to-read';

const OPTIONS_LIMIT = 200;

const pct = (value: number) => formatPercent(value, { digits: 1, fixed: true });

export function JobStatus({ state }: { state: ReturnType<typeof useJob> }) {
  const { start, job, cancel } = state;
  return (
    <>
      {start.isError && <ErrorState error={start.error} retry={() => start.reset()} />}
      {job.isError && <ErrorState error={job.error} retry={() => void job.refetch()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <div className="mt-3 space-y-2 text-sm text-muted-foreground">
          {['queued', 'running'].includes(job.data.status) && (
            <ProgressBar
              value={job.data.progress}
              phase={job.data.phase}
              status={job.data.status}
            />
          )}
          Trabajo #{job.data.id.slice(0, 8)} · {job.data.status}
          {['queued', 'running'].includes(job.data.status) && (
            <Button
              className="ml-3"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Solicitar cancelación
            </Button>
          )}
          {job.data.status === 'failed' && (
            <p className="mt-2 text-destructive">
              El cálculo no terminó. Comprueba que los experimentos siguen existiendo.
            </p>
          )}
        </div>
      )}
    </>
  );
}

function useReturnExperiments() {
  return useQuery({
    queryKey: ['research', 'experiments', '', '', 0, OPTIONS_LIMIT],
    queryFn: ({ signal }) =>
      getExperiments({ family: '', stage: '', offset: 0, limit: OPTIONS_LIMIT }, signal),
    select: (data) => data.items.filter((item) => item.has_returns),
  });
}

function label(item: ExperimentSummary): string {
  return item.sharpe != null
    ? `#${item.id} · ${item.model_id} · Sharpe ${formatNumber(item.sharpe, { digits: 2, fixed: true })}`
    : `#${item.id} · ${item.model_id}`;
}

function PboResult({ jobId }: { jobId: string }) {
  const result = useQuery({
    queryKey: ['research', 'experiment-pbo', jobId],
    queryFn: ({ signal }) => getExperimentPbo(jobId, signal),
  });
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  const data = result.data;
  return (
    <div className="mt-4 space-y-2 text-sm" role="region" aria-label="Resultado PBO">
      {data.pbo == null ? (
        <p className="text-amber-700 dark:text-amber-400">{data.message}</p>
      ) : (
        <>
          <p
            className="text-2xl font-semibold"
            title="Fracción de particiones en las que la mejor variante dentro de muestra queda por debajo de la mediana fuera de muestra. Cerca de 0 % = la elección se sostiene; cerca de 50 % = elegir «la mejor» no aporta nada, es ruido."
          >
            PBO {pct(data.pbo)}
          </p>
          <p className="text-xs text-muted-foreground">
            {data.n_combinations} combinaciones IS/OOS evaluadas · {data.n_splits} bloques ·{' '}
            {data.n_common_dates} fechas comunes ({dateText(data.first_date)} –{' '}
            {dateText(data.last_date)}).
          </p>
        </>
      )}
      <a
        className="inline-block text-primary underline"
        href={'/api/v1/jobs/' + data.job_id + '/result'}
        download={'gabi-pbo-' + data.job_id + '.json'}
      >
        Descargar resultado con procedencia
      </a>
    </div>
  );
}

export function PboPanel() {
  const experiments = useReturnExperiments();
  const [picked, setPicked] = useState<number[]>([]);
  const state = useJob('pbo');
  const options = experiments.data ?? [];
  return (
    <section className="rounded-xl border bg-card p-5" aria-label="PBO CSCV">
      <h2 className="text-lg font-semibold">
        <Term k="pbo">Probabilidad de sobreajuste (PBO)</Term>
      </h2>
      <HowToRead className="mt-1">
        Elige la mejor variante dentro de una muestra y comprueba si esa elección se sostiene fuera
        de ella. Requiere retornos observados sobre las mismas fechas de al menos 2 experimentos:
        solo los registrados con su serie de retornos. Se ejecuta como trabajo explícito porque con
        16 bloques evalúa 12.870 particiones.
      </HowToRead>
      {experiments.isError && (
        <ErrorState error={experiments.error} retry={() => void experiments.refetch()} />
      )}
      {experiments.data && options.length < 2 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Hacen falta al menos 2 experimentos con serie de retornos guardada.
        </p>
      ) : (
        <fieldset className="mt-3 grid gap-1 text-sm">
          <legend className="mb-1">Variantes a comparar (mínimo 2)</legend>
          {options.map((item) => (
            <label key={item.id} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={picked.includes(item.id)}
                onChange={(event) => {
                  state.setJobId(null);
                  setPicked((current) =>
                    event.target.checked
                      ? [...current, item.id].slice(0, 20)
                      : current.filter((id) => id !== item.id),
                  );
                }}
              />
              {label(item)}
            </label>
          ))}
        </fieldset>
      )}
      <Button
        className="mt-3"
        disabled={picked.length < 2 || state.start.isPending}
        onClick={() => {
          state.setJobId(null);
          state.start.mutate({
            kind: 'experiment_pbo',
            experiment_analysis: { experiment_ids: picked },
          });
        }}
      >
        Calcular PBO
      </Button>
      <JobStatus state={state} />
      {state.jobId && state.job.data?.status === 'succeeded' && <PboResult jobId={state.jobId} />}
    </section>
  );
}

function BootstrapResult({ jobId }: { jobId: string }) {
  const result = useQuery({
    queryKey: ['research', 'experiment-bootstrap', jobId],
    queryFn: ({ signal }) => getExperimentBootstrap(jobId, signal),
  });
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  const data = result.data;
  return (
    <div className="mt-4" role="region" aria-label="Resultado del bootstrap">
      {data.view == null ? (
        <p className="text-sm text-amber-700 dark:text-amber-400">{data.message}</p>
      ) : (
        <BlockBootstrapResult
          view={data.view}
          downloads={{
            json: '/api/v1/jobs/' + data.job_id + '/result',
            csv: '/api/v1/research/experiment-bootstrap/' + data.job_id + '/distributions.csv',
          }}
        />
      )}
    </div>
  );
}

export function BootstrapPanel() {
  const experiments = useReturnExperiments();
  const [strategy, setStrategy] = useState(0);
  const [benchmark, setBenchmark] = useState(0);
  const state = useJob('bootstrap');
  const options = experiments.data ?? [];
  const selected = options.find((item) => item.id === strategy);
  const comparable = options.filter(
    (item) =>
      selected != null &&
      item.id !== selected.id &&
      item.periods_per_year === selected.periods_per_year,
  );
  return (
    <section className="rounded-xl border bg-card p-5" aria-label="Incertidumbre por bloques">
      <h2 className="text-lg font-semibold">
        <Term k="block_bootstrap">Incertidumbre por bloques temporales</Term>
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Distribuciones de rentabilidad, riesgo y exceso frente a un benchmark sobre las mismas
        fechas. Método y sensibilidad fijados de antemano; no se optimizan pesos ni se repiten
        backtests.
      </p>
      {experiments.isError && (
        <ErrorState error={experiments.error} retry={() => void experiments.refetch()} />
      )}
      {experiments.data && options.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Hacen falta experimentos con serie de retornos guardada.
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          <label className="grid gap-1">
            Experimento para calcular incertidumbre
            <NativeSelect
              value={String(strategy)}
              onChange={(event) => {
                setStrategy(Number(event.target.value));
                setBenchmark(0);
                state.setJobId(null);
              }}
            >
              <NativeSelectOption value="0">Elige un experimento</NativeSelectOption>
              {options.map((item) => (
                <NativeSelectOption key={item.id} value={String(item.id)}>
                  #{item.id} · {item.model_id}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
          <label className="grid gap-1">
            Serie de comparación (misma frecuencia y fechas)
            <NativeSelect
              value={String(benchmark)}
              disabled={strategy === 0}
              onChange={(event) => {
                setBenchmark(Number(event.target.value));
                state.setJobId(null);
              }}
            >
              <NativeSelectOption value="0">Sin benchmark</NativeSelectOption>
              {comparable.map((item) => (
                <NativeSelectOption key={item.id} value={String(item.id)}>
                  #{item.id} · {item.model_id}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
        </div>
      )}
      <Button
        className="mt-3"
        disabled={strategy === 0 || state.start.isPending}
        onClick={() => {
          state.setJobId(null);
          state.start.mutate({
            kind: 'experiment_bootstrap',
            experiment_analysis: {
              experiment_id: strategy,
              benchmark_id: benchmark === 0 ? null : benchmark,
            },
          });
        }}
      >
        Calcular distribuciones e intervalos
      </Button>
      <JobStatus state={state} />
      {state.jobId && state.job.data?.status === 'succeeded' && (
        <BootstrapResult jobId={state.jobId} />
      )}
    </section>
  );
}
