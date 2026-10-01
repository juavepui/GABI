import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDeflatedSharpe, getExperimentTailRisk, getExperiments } from '@/shared/api/client';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { TailRiskTable } from './tail-risk-table';

// Selectors read one bounded page; the backend recomputes N from the whole family.
const OPTIONS_LIMIT = 200;

const pct = (value: number) =>
  new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(
    value * 100,
  ) + ' %';
const num = (value: number) =>
  new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2, minimumFractionDigits: 2 }).format(
    value,
  );

function DeflatedSharpeResult({ id, family }: { id: number; family: string }) {
  const result = useQuery({
    queryKey: ['research', 'deflated-sharpe', id, family],
    queryFn: ({ signal }) => getDeflatedSharpe(id, family, signal),
  });
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  const data = result.data;
  return (
    <div className="mt-4 space-y-3" role="region" aria-label="Resultado PSR y DSR">
      <p className="text-xs text-muted-foreground">
        {data.moments === 'returns'
          ? 'Serie disponible: PSR/DSR con asimetría y curtosis estimadas. La inferencia sigue siendo aproximada.'
          : 'Sin serie de retornos guardada para este experimento: PSR/DSR con aproximación normal (asimetría 0, curtosis 3).'}
      </p>
      <dl className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border p-3">
          <dt
            className="text-xs text-muted-foreground"
            title="Probabilidad de que el Sharpe sea genuinamente positivo, sin corregir por nº de intentos."
          >
            PSR (frente a Sharpe = 0)
          </dt>
          <dd className="text-xl font-semibold">{pct(data.psr)}</dd>
        </div>
        <div className="rounded-lg border p-3">
          <dt
            className="text-xs text-muted-foreground"
            title="Sharpe que cabría esperar por pura casualidad entre N intentos sin ventaja real."
          >
            SR*₀ (máximo esperado por azar)
          </dt>
          <dd className="text-xl font-semibold">{num(data.sr0_benchmark)}</dd>
        </div>
        <div className="rounded-lg border p-3">
          <dt
            className="text-xs text-muted-foreground"
            title="Probabilidad de que el Sharpe sea genuinamente positivo, ya corregida por haber probado N configuraciones."
          >
            DSR (deflactado)
          </dt>
          <dd className="text-xl font-semibold">{pct(data.dsr)}</dd>
        </div>
      </dl>
      <p className="text-sm">
        Con N={data.n_trials} intentos probados
        {data.family ? ` en la familia «${data.family}»` : ''}, el Sharpe de {num(data.sharpe)} del
        experimento #{data.experiment_id} tiene un DSR de {pct(data.dsr)}:{' '}
        {data.dsr > 0.95
          ? 'sigue pareciendo genuino incluso corrigiendo por multiple testing.'
          : 'convendría más evidencia (out-of-sample o más historia) antes de confiar en él.'}
      </p>
    </div>
  );
}

export function DeflatedSharpePanel({ families }: { families: string[] }) {
  const [family, setFamily] = useState(families[0] ?? '');
  const [selected, setSelected] = useState(0);
  const rows = useQuery({
    queryKey: ['research', 'experiments', family, '', 0, OPTIONS_LIMIT],
    queryFn: ({ signal }) =>
      getExperiments({ family, stage: '', offset: 0, limit: OPTIONS_LIMIT }, signal),
  });
  const options = (rows.data?.items ?? []).filter((item) => item.sharpe != null);
  return (
    <section className="rounded-xl border bg-card p-5" aria-label="Probabilistic y Deflated Sharpe">
      <h2 className="text-lg font-semibold">Probabilistic / Deflated Sharpe Ratio</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        PSR: probabilidad de que el Sharpe observado sea genuinamente positivo y no ruido de
        muestreo. DSR: lo mismo, pero comparando con el Sharpe máximo que cabría esperar por azar
        entre todos los intentos de la familia elegida; corrige por haber probado varias
        configuraciones.
      </p>
      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        {families.length > 0 && (
          <label className="grid gap-1">
            Familia de intentos (define N)
            <NativeSelect
              value={family}
              onChange={(event) => {
                setFamily(event.target.value);
                setSelected(0);
              }}
            >
              {families.map((name) => (
                <NativeSelectOption key={name} value={name}>
                  {name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
        )}
        {options.length >= 2 && (
          <label className="grid gap-1">
            Experimento a evaluar
            <NativeSelect
              value={String(selected)}
              onChange={(event) => setSelected(Number(event.target.value))}
            >
              <NativeSelectOption value="0">Elige un experimento</NativeSelectOption>
              {options.map((item) => (
                <NativeSelectOption key={item.id} value={String(item.id)}>
                  #{item.id} · {item.model_id} · {item.n_positions ?? '—'} pos ·{' '}
                  {item.rebalance ?? '—'} · Sharpe {num(item.sharpe!)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
        )}
      </div>
      {rows.isPending && <LoadingState />}
      {rows.isError && <ErrorState error={rows.error} retry={() => void rows.refetch()} />}
      {rows.data && rows.data.total > OPTIONS_LIMIT && (
        <p className="mt-3 text-sm text-muted-foreground">
          Solo se listan los {OPTIONS_LIMIT} experimentos más recientes; N incluye toda la familia.
        </p>
      )}
      {rows.data && options.length < 2 && (
        <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">
          Esta familia tiene menos de 2 experimentos con Sharpe: no se puede calcular DSR (hacen
          falta al menos 2 intentos para estimar cuánto varía el Sharpe entre ellos por azar).
        </p>
      )}
      {selected > 0 && <DeflatedSharpeResult id={selected} family={family} />}
    </section>
  );
}

function TailResult({ id }: { id: number }) {
  const result = useQuery({
    queryKey: ['research', 'experiment-tail', id],
    queryFn: ({ signal }) => getExperimentTailRisk(id, signal),
  });
  if (result.isPending) return <LoadingState />;
  if (result.isError)
    return <ErrorState error={result.error} retry={() => void result.refetch()} />;
  return (
    <div role="region" aria-label="Riesgo de cola del experimento">
      <TailRiskTable
        horizon={result.data.horizon}
        series={result.data.series}
        message={result.data.message}
      />
    </div>
  );
}

export function ExperimentTailPanel() {
  const [selected, setSelected] = useState(0);
  const rows = useQuery({
    queryKey: ['research', 'experiments', '', '', 0, OPTIONS_LIMIT],
    queryFn: ({ signal }) =>
      getExperiments({ family: '', stage: '', offset: 0, limit: OPTIONS_LIMIT }, signal),
  });
  const options = (rows.data?.items ?? []).filter((item) => item.has_returns);
  if (rows.isError) return <ErrorState error={rows.error} retry={() => void rows.refetch()} />;
  if (options.length === 0) return null;
  return (
    <details className="rounded-xl border bg-card p-5 text-sm">
      <summary className="cursor-pointer font-medium">
        Riesgo de cola · serie guardada de un experimento
      </summary>
      <label className="mt-3 grid w-fit gap-1">
        Experimento con retornos
        <NativeSelect
          value={String(selected)}
          onChange={(event) => setSelected(Number(event.target.value))}
        >
          <NativeSelectOption value="0">Elige un experimento</NativeSelectOption>
          {options.map((item) => (
            <NativeSelectOption key={item.id} value={String(item.id)}>
              #{item.id} · {item.model_id}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </label>
      {selected > 0 && <TailResult id={selected} />}
    </details>
  );
}
