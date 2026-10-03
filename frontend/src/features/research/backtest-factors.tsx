import { lazy, Suspense, useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { cancelJob, createJob, getBacktestFactors, getJob } from '@/shared/api/client';
import type {
  BacktestFactorsPreview,
  FactorBenchmark,
  FactorStability,
  StabilityFit,
} from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatNumber, formatPercent } from '@/shared/lib/format';
import { HowToRead } from '@/shared/ui/how-to-read';
import { NativeSelect } from '@/shared/ui/native-select';

const RollingChart = lazy(() =>
  import('./backtest-factor-charts').then((module) => ({ default: module.RollingChart })),
);
const WealthChart = lazy(() =>
  import('./backtest-factor-charts').then((module) => ({ default: module.WealthChart })),
);

const FACTORS: [string, string][] = [
  ['Mkt-RF', 'Exposición al mercado (~1 = se mueve como la bolsa en general)'],
  ['SMB', 'Tamaño (small minus big): inclinación hacia empresas más pequeñas'],
  ['HML', 'Value (high minus low book-to-market)'],
  ['RMW', 'Calidad/rentabilidad (robust minus weak)'],
  ['CMA', 'Inversión (conservative minus aggressive)'],
  ['Mom', 'Momentum'],
];
const COEFFICIENTS = ['alpha', ...FACTORS.map(([name]) => name)];
const LABELS: Record<string, string> = {
  strategy: 'Estrategia',
  spy: 'SPY',
  rf: 'RF',
  universe_ew: 'Universo EW',
  spy_beta: 'SPY ajustado por beta',
  ff6: 'FF5 + Momentum sin alfa',
};
const num = (value: number | null | undefined, digits = 3) => formatNumber(value, { digits });
const pct = (value: number | null | undefined, digits = 2) => formatPercent(value, { digits });
const signed = (value: number | null | undefined, digits = 2) =>
  value == null ? '—' : (value > 0 ? '+' : '') + num(value, digits);

export function BacktestFactors({
  sourceJobId,
  periods,
}: {
  sourceJobId: string;
  periods: number;
}) {
  const [automatic, setAutomatic] = useState(true);
  const [lags, setLags] = useState(Math.min(3, Math.max(periods - 1, 0)));
  const [jobId, setJobId] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'backtest_factors',
        factor_contrast: { source_job_id: sourceJobId, hac_lags: automatic ? null : lags },
        idempotency_key: 'factors-ff:' + crypto.randomUUID(),
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
    queryKey: ['research', 'backtest-factors', jobId],
    queryFn: ({ signal }) => getBacktestFactors(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJobId(null);
    run.mutate();
  }

  return (
    <details className="rounded-lg border p-4 text-sm">
      <summary className="cursor-pointer font-medium">
        Contraste con factores académicos (Fama-French 5 + Momentum)
      </summary>
      <HowToRead className="mt-2">
        ¿Lo que hace la estrategia es distinto de las primas de factor documentadas (mercado,
        tamaño, value, calidad, inversión y momentum de la Kenneth French Data Library)? Se
        regresiona el retorno de la estrategia contra esos seis factores; el alfa es lo que queda
        sin explicar. Usa la copia local de los factores y solo la descarga si no existe.
      </HowToRead>
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-2 text-xs font-medium">
          <input
            type="checkbox"
            checked={automatic}
            onChange={(event) => setAutomatic(event.target.checked)}
          />
          Elegir retardos HAC automáticamente
        </label>
        {!automatic && (
          <label className="text-xs font-medium">
            Máximo retardo (periodos del backtest)
            <Input
              className="mt-1.5"
              type="number"
              min={0}
              max={Math.max(periods - 1, 0)}
              step={1}
              value={lags}
              onChange={(event) => setLags(Number(event.target.value))}
            />
          </label>
        )}
        <Button type="submit" disabled={run.isPending}>
          Calcular contraste
        </Button>
      </form>
      <p className="mt-2 text-xs text-muted-foreground">
        0 retardos corrige heterocedasticidad; más retardos también autocorrelación. Elige el
        criterio antes de mirar qué t-stat produce.
      </p>
      {run.isError && <ErrorState error={run.error} retry={() => run.mutate()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <p className="mt-3 text-muted-foreground">
          Contraste #{job.data.id.slice(0, 8)} · {job.data.phase} · {job.data.status}
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
        <p className="mt-2 text-destructive">
          No se pudo calcular: revisa que los retardos no superen los periodos y que haya factores
          locales o conexión para descargarlos.
        </p>
      )}
      {preview.isPending && job.data?.status === 'succeeded' && <LoadingState />}
      {preview.isError && <ErrorState error={preview.error} retry={() => void preview.refetch()} />}
      {preview.data && <FactorResult result={preview.data} />}
    </details>
  );
}

function FactorResult({ result }: { result: BacktestFactorsPreview }) {
  const reg = result.regression;
  return (
    <section className="mt-4 space-y-5" aria-label="Contraste Fama-French">
      {reg ? (
        <div>
          <dl className="grid gap-3 sm:grid-cols-3">
            <Stat label="Alfa anualizado" value={pct(reg.alpha_anualizado)} />
            <Stat label="t-stat del alfa (HAC)" value={signed(reg.t_stat.alpha)} />
            <Stat label="R² de la regresión" value={num(reg.r2, 2)} />
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">
            Regresión con {reg.periodos_alineados}/{reg.periodos_totales} periodos alineados (
            {reg.dof} grados de libertad tras 6 factores + alfa). HAC/Newey-West: Bartlett,{' '}
            {reg.hac_lags} retardos, corrección n/(n−k). t-stat del alfa OLS convencional:{' '}
            {signed(reg.t_stat_ols.alpha)}. |t| ≈ 2 es solo una referencia asintótica; con muchas
            configuraciones probadas conviene exigir más de 3. HAC no corrige el multiple testing.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2">Factor</th>
                  <th>Qué mide</th>
                  <th>Beta</th>
                  <th>SE (HAC)</th>
                  <th>t-stat (HAC)</th>
                </tr>
              </thead>
              <tbody>
                {FACTORS.map(([name, label]) => (
                  <tr key={name} className="border-b last:border-0">
                    <td className="py-2">{name}</td>
                    <td>{label}</td>
                    <td>{num(reg.coef[name])}</td>
                    <td>{num(reg.se[name])}</td>
                    <td>{signed(reg.t_stat[name])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="text-muted-foreground">
          No se pudo calcular el contraste: {result.regression_error}
        </p>
      )}
      <Stability audit={result.stability ?? null} error={result.stability_error} />
      <Benchmark audit={result.benchmark ?? null} error={result.benchmark_error} />
      <p className="text-xs text-muted-foreground">
        Factores: {result.factors_source.file} ({result.factors_source.first_month} a{' '}
        {result.factors_source.last_month}), SHA-256 {result.factors_source.sha256.slice(0, 12)}… ·
        Fuente: Kenneth French Data Library.
      </p>
      <a
        className="inline-block text-sm text-primary underline"
        href={'/api/v1/jobs/' + result.job_id + '/result'}
        download={'gabi-fama-french-' + result.job_id + '.json'}
      >
        Descargar contraste completo
      </a>
      <p className="break-all text-xs text-muted-foreground">SHA-256: {result.result_sha256}</p>
    </section>
  );
}

function fitRow(label: string, fit: StabilityFit) {
  return (
    <tr key={label} className="border-b last:border-0">
      <td className="py-2">{label}</td>
      <td>{fit.start ?? '—'}</td>
      <td>{fit.end ?? '—'}</td>
      <td>{fit.n_obs}</td>
      <td>{fit.status}</td>
      <td>{pct(fit.alpha_anualizado)}</td>
      <td>{signed(fit.t_stat?.alpha)}</td>
      {FACTORS.map(([name]) => (
        <td key={name}>{num(fit.coef?.[name])}</td>
      ))}
    </tr>
  );
}

export function Stability({
  audit,
  error,
}: {
  audit: FactorStability | null;
  error?: string | null;
}) {
  const [coefficient, setCoefficient] = useState('alpha');
  const [windowSize, setWindowSize] = useState(16);
  if (!audit) {
    return <p className="text-muted-foreground">{error}</p>;
  }
  const points = audit.rolling
    .filter((fit) => fit.window === windowSize && fit.coef?.[coefficient] != null)
    .map((fit) => ({
      end: fit.end ?? '',
      estimate: fit.coef![coefficient]!,
      low: fit.ci95_pointwise?.[coefficient]?.[0] ?? fit.coef![coefficient]!,
      high: fit.ci95_pointwise?.[coefficient]?.[1] ?? fit.coef![coefficient]!,
    }));
  return (
    <div className="space-y-3">
      <h4 className="font-semibold">Estabilidad temporal de alfa y betas</h4>
      <p className="text-xs text-muted-foreground">
        {audit.n_obs} trimestres · FF5 + Momentum. Diagnóstico retrospectivo; intervalos HAC
        puntuales y aproximados.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Muestra</th>
              <th>Desde</th>
              <th>Hasta</th>
              <th>n</th>
              <th>Estado</th>
              <th>Alfa anualizado</th>
              <th>t alfa HAC</th>
              {FACTORS.map(([name]) => (
                <th key={name}>Beta {name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fitRow('Completa', audit.full)}
            {audit.halves[0] && fitRow('Primera mitad', audit.halves[0])}
            {audit.halves[1] && fitRow('Segunda mitad', audit.halves[1])}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-3">
        <label className="text-xs font-medium">
          Coeficiente
          <NativeSelect
            className="mt-1.5"
            value={coefficient}
            onChange={(event) => setCoefficient(event.target.value)}
          >
            {COEFFICIENTS.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="text-xs font-medium">
          Ventana (trimestres)
          <NativeSelect
            className="mt-1.5"
            value={windowSize}
            onChange={(event) => setWindowSize(Number(event.target.value))}
          >
            {[16, 20, 24].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </NativeSelect>
        </label>
      </div>
      {points.length === 0 ? (
        <p className="text-muted-foreground">La muestra no alcanza la longitud de esta ventana.</p>
      ) : (
        <Suspense fallback={<p>Preparando gráfico…</p>}>
          <RollingChart points={points} full={audit.full.coef?.[coefficient] ?? null} />
        </Suspense>
      )}
      <p className="text-xs text-muted-foreground">
        Las ventanas se solapan. Los cambios visuales y los intervalos puntuales no prueban un
        cambio de régimen.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Episodio</th>
              <th>n</th>
              <th>Retorno compuesto</th>
              <th>Contribución al alfa trimestral global (pp)</th>
              <th>Regresión local</th>
              <th>Alfa anualizado al excluir episodio</th>
            </tr>
          </thead>
          <tbody>
            {audit.events.map((event) => (
              <tr key={event.id} className="border-b last:border-0">
                <td className="py-2">{event.label}</td>
                <td>{event.n_obs}</td>
                <td>{pct(event.compounded_return)}</td>
                <td>
                  {event.attribution.contribution_to_full_quarterly_alpha == null
                    ? '—'
                    : num(event.attribution.contribution_to_full_quarterly_alpha * 100)}
                </td>
                <td>{String(event.local_regression.status)}</td>
                <td>{pct(event.without_episode?.alpha_anualizado)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <HowToRead>
        Contribución = suma de (exceso de retorno − exposición a factores con betas globales) / n
        total. Las filas suman el alfa trimestral global; no son alfas por episodio.
        insufficient_data significa que no se estiman alfa y betas locales con tan pocas
        observaciones.
      </HowToRead>
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
        {audit.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function Benchmark({
  audit,
  error,
}: {
  audit: FactorBenchmark | null;
  error?: string | null;
}) {
  const [mode, setMode] = useState<'expanding' | 'in_sample'>('expanding');
  if (!audit) {
    return <p className="text-muted-foreground">{error}</p>;
  }
  const selected = audit[mode];
  const comparison = {
    ...selected,
    metrics: selected.metrics ?? {},
    active: selected.active ?? {},
    periods: selected.periods ?? [],
  };
  const series = Object.keys(comparison.metrics);
  const points = [
    { date: comparison.start ?? '', ...Object.fromEntries(series.map((name) => [name, 1])) },
    ...comparison.periods.map((row) => ({ date: row.hasta, ...row.wealth })),
  ];
  return (
    <div className="space-y-3">
      <h4 className="font-semibold">Benchmark ajustado por beta y factores</h4>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Estimación de exposiciones">
        <Button
          type="button"
          size="sm"
          variant={mode === 'expanding' ? 'default' : 'outline'}
          aria-pressed={mode === 'expanding'}
          onClick={() => setMode('expanding')}
        >
          Expansiva con datos anteriores
        </Button>
        <Button
          type="button"
          size="sm"
          variant={mode === 'in_sample' ? 'default' : 'outline'}
          aria-pressed={mode === 'in_sample'}
          onClick={() => setMode('in_sample')}
        >
          Muestra completa (atribución retrospectiva)
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {mode === 'in_sample'
          ? 'Estas betas utilizan toda la muestra, incluidos los periodos representados. Es un diagnóstico retrospectivo, no un backtest sin anticipación.'
          : `Mínimo ${audit.method.min_train} trimestres de entrenamiento y ${audit.method.embargo_quarters} de embargo, sin alfa en el benchmark. Los factores históricos revisados no certifican disponibilidad point-in-time.`}
      </p>
      {!comparison.n_obs ? (
        <p className="text-muted-foreground">
          No hay suficiente historia tras entrenamiento y embargo para construir esta comparación.
        </p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {comparison.n_obs} trimestres: {comparison.start} → {comparison.end}. Todas las curvas
            parten de 1 en la misma fecha.
          </p>
          <Suspense fallback={<p>Preparando gráfico…</p>}>
            <WealthChart points={points} series={series} labels={LABELS} />
          </Suspense>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-xs">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2">Referencia</th>
                  <th>Retorno acumulado</th>
                  <th>CAGR</th>
                  <th>Exceso medio trimestral</th>
                  <th>Diferencia de CAGR (pp)</th>
                  <th>Exceso de riqueza relativa</th>
                </tr>
              </thead>
              <tbody>
                {series.map((name) => (
                  <tr key={name} className="border-b last:border-0">
                    <td className="py-2">{LABELS[name] ?? name}</td>
                    <td>{pct(comparison.metrics[name]?.total_return)}</td>
                    <td>{pct(comparison.metrics[name]?.cagr)}</td>
                    <td>{pct(comparison.active[name]?.mean_active_per_quarter)}</td>
                    <td>
                      {comparison.active[name]?.cagr_difference == null
                        ? '—'
                        : num(comparison.active[name]!.cagr_difference! * 100, 2)}
                    </td>
                    <td>{pct(comparison.active[name]?.relative_wealth_return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">
            Exceso de riqueza = capital estrategia / capital benchmark − 1. La diferencia de CAGR no
            es el alfa de regresión; el exceso tampoco prueba habilidad de selección.
          </p>
        </>
      )}
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
        {audit.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-medium">{value}</dd>
    </div>
  );
}
