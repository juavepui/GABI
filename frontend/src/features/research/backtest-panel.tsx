import { lazy, Suspense, useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  cancelJob,
  createJob,
  getBacktestPreview,
  getJob,
  getJobResult,
} from '@/shared/api/client';
import type {
  BacktestDefaults,
  BacktestOptions,
  BacktestPreview,
} from '@/shared/api/generated/types.gen';
import { useFormDefaults } from '@/shared/api/use-form-defaults';
import { AdvancedOptions, HelpField } from '@/shared/ui/advanced-options';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { BacktestDiagnostics } from './backtest-diagnostics';
import { BacktestFactors } from './backtest-factors';
import { BacktestRegister } from './backtest-register';
import { V3ComparisonResult, type V3Comparison } from './backtest-v3-comparison';
import { PrepareData } from './prepare-data';
import { dateText, formatNumber, formatPercent } from '@/shared/lib/format';
import { HowToRead } from '@/shared/ui/how-to-read';
import { ResearchModeNotice } from '@/shared/ui/research-mode';
import { NativeSelect } from '@/shared/ui/native-select';
import { Hash } from '@/shared/ui/hash';

const BacktestChart = lazy(() => import('./backtest-chart'));

type Engine = 'backtest_v1' | 'backtest_v2' | 'backtest_v3_comparison';

const selectClass = 'mt-1.5 w-full';
const pct = (value: number | null | undefined, digits = 1) => formatPercent(value, { digits });
const num = (value: number | null | undefined, digits = 2) => formatNumber(value, { digits });
const SERIES = { estrategia: 'Estrategia', universo_ew: 'Universo equiponderado', spy: 'SPY' };

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="text-xs font-medium">
      {label}
      {children}
    </label>
  );
}

/** Waits for the backend's defaults (#190), the panel's initial state. */
export function BacktestPanel({ researchAllowed }: { researchAllowed: boolean }) {
  const defaults = useFormDefaults();
  if (defaults.isPending) return <LoadingState />;
  if (defaults.isError)
    return <ErrorState error={defaults.error} retry={() => void defaults.refetch()} />;
  return <Panel researchAllowed={researchAllowed} defaults={defaults.data.backtest} />;
}

function Panel({
  researchAllowed,
  defaults,
}: {
  researchAllowed: boolean;
  defaults: BacktestDefaults;
}) {
  const [engine, setEngine] = useState<Engine>('backtest_v1');
  const [start, setStart] = useState(defaults.start);
  const [end, setEnd] = useState(defaults.end);
  const [months, setMonths] = useState<1 | 3 | 6 | 12>(defaults.months);
  const [topN, setTopN] = useState(defaults.top_n_v1);
  const [hurdle, setHurdle] = useState(defaults.rotation_hurdle_points);
  const [costBps, setCostBps] = useState(defaults.cost_bps);
  const [universe, setUniverse] = useState<50 | 100 | 500>(defaults.universe_size);
  const [mode, setMode] = useState<'fast_dev' | 'validation'>(defaults.mode);
  const [sample, setSample] = useState<50 | 100 | 200>(defaults.max_symbols);
  const [capital, setCapital] = useState(defaults.initial_capital);
  const [commission, setCommission] = useState(defaults.commission_usd);
  const [spread, setSpread] = useState(defaults.spread_bps);
  const [jobId, setJobId] = useState<string | null>(null);

  const options = (): BacktestOptions =>
    engine === 'backtest_v1'
      ? {
          months,
          top_n: topN,
          rotation_hurdle_points: hurdle,
          cost_bps: costBps,
          universe_size: universe,
        }
      : {
          months,
          top_n: topN,
          rotation_hurdle_points: hurdle,
          mode,
          max_symbols: mode === 'fast_dev' ? sample : null,
          initial_capital: capital,
          commission_usd: commission,
          spread_bps: spread,
        };
  const run = useMutation({
    mutationFn: () =>
      createJob({
        kind: engine,
        start,
        end,
        backtest_options: options(),
        idempotency_key: 'backtest:' + crypto.randomUUID(),
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
  const comparing = job.data?.kind === 'backtest_v3_comparison';
  const preview = useQuery({
    queryKey: ['research', 'backtests', jobId],
    queryFn: ({ signal }) => getBacktestPreview(jobId!, signal),
    enabled: job.data?.status === 'succeeded' && !comparing,
  });
  const comparison = useQuery({
    queryKey: ['job', jobId, 'result'],
    queryFn: ({ signal }) => getJobResult(jobId!, signal) as Promise<V3Comparison>,
    enabled: job.data?.status === 'succeeded' && comparing,
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId!) });

  function selectEngine(next: Engine) {
    setEngine(next);
    setTopN(next === 'backtest_v1' ? defaults.top_n_v1 : defaults.top_n_v2);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJobId(null);
    run.mutate();
  }

  return (
    <section className="space-y-4" aria-labelledby="backtest-heading">
      <div>
        <h2 id="backtest-heading" className="text-2xl font-semibold">
          Backtest multifactor por rebalanceos
        </h2>
        <HowToRead className="mt-2">
          Reconstruye el ranking en cada fecha con SEC EDGAR y la composición histórica del índice,
          solo dentro del periodo observado de 2010 a julio de 2025. Un periodo sin cobertura se
          salta y se lista. Es un ensayo retrospectivo: no demuestra ventaja frente al S&amp;P 500.
        </HowToRead>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Motor del backtest">
        <Button
          type="button"
          variant={engine === 'backtest_v1' ? 'default' : 'outline'}
          aria-pressed={engine === 'backtest_v1'}
          onClick={() => selectEngine('backtest_v1')}
        >
          Motor V1 (clásico)
        </Button>
        <Button
          type="button"
          variant={engine === 'backtest_v2' ? 'default' : 'outline'}
          aria-pressed={engine === 'backtest_v2'}
          onClick={() => selectEngine('backtest_v2')}
        >
          Motor V2 (contabilidad real)
        </Button>
        <Button
          type="button"
          variant={engine === 'backtest_v3_comparison' ? 'default' : 'outline'}
          aria-pressed={engine === 'backtest_v3_comparison'}
          onClick={() => selectEngine('backtest_v3_comparison')}
        >
          Comparar V2 y V3
        </Button>
      </div>
      <p className="max-w-3xl text-sm text-muted-foreground">
        {engine === 'backtest_v1'
          ? 'V1 cobra un coste plano de compra y venta sobre cada posición nueva y compara con el universo equiponderado y el SPY. Los universos de 50 o 100 empresas son pruebas parciales.'
          : engine === 'backtest_v3_comparison'
            ? 'Ejecuta V2 con estas opciones y después V3 sobre las mismas selecciones y datos, con costes como V2, base y estrés, más la validación de la política de #248. Es un diagnóstico del motor; tarda algo más que V2.'
            : 'V2 opera con acciones y caja, comisión fija y spread sobre los ajustes reales, SPY comprado y mantenido y curva diaria. Solo el universo completo es citable; la muestra rápida sirve para iterar.'}
      </p>
      {!researchAllowed && <ResearchModeNotice action="Ejecutar backtests" />}
      <form
        onSubmit={submit}
        className="grid gap-4 rounded-xl border bg-card p-5 sm:grid-cols-2 lg:grid-cols-4"
      >
        <Field label="Inicio">
          <Input
            className="mt-1.5"
            type="date"
            min="2010-01-01"
            max="2025-07-02"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            required
          />
        </Field>
        <Field label="Fin">
          <Input
            className="mt-1.5"
            type="date"
            min="2010-01-01"
            max="2025-07-02"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            required
          />
        </Field>
        <Field label="Rebalanceo">
          <NativeSelect
            className={selectClass}
            value={months}
            onChange={(event) => setMonths(Number(event.target.value) as 1 | 3 | 6 | 12)}
          >
            {[1, 3, 6, 12].map((value) => (
              <option key={value} value={value}>
                Cada {value} meses
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Empresas por periodo">
          <Input
            className="mt-1.5"
            type="number"
            min={1}
            max={50}
            step={1}
            value={topN}
            onChange={(event) => setTopN(Number(event.target.value))}
            required
          />
        </Field>
        <AdvancedOptions id="backtest" className="sm:col-span-2 lg:col-span-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <HelpField
              id="backtest-hurdle"
              label="Umbral de rotación (puntos Composite)"
              help="Puntos de score que debe superar una candidata nueva para sustituir a una posición. Más alto: menos rotación y menos costes."
              className="text-xs font-medium"
            >
              <Input
                id="backtest-hurdle"
                className="mt-1.5"
                type="number"
                min={0}
                max={100}
                step={1}
                value={hurdle}
                onChange={(event) => setHurdle(Number(event.target.value))}
                required
              />
            </HelpField>
            {engine === 'backtest_v1' ? (
              <>
                <HelpField
                  id="backtest-cost"
                  label="Coste por lado (pb)"
                  help="Puntos básicos (1 pb = 0,01 %) cobrados al comprar y otra vez al vender cada posición nueva."
                  className="text-xs font-medium"
                >
                  <Input
                    id="backtest-cost"
                    className="mt-1.5"
                    type="number"
                    min={0}
                    max={500}
                    step={0.5}
                    value={costBps}
                    onChange={(event) => setCostBps(Number(event.target.value))}
                    required
                  />
                </HelpField>
                <HelpField
                  id="backtest-universe"
                  label="Universo"
                  help="Empresas reconstruidas en cada fecha. 50 o 100 son pruebas parciales; 500 es el índice completo."
                  className="text-xs font-medium"
                >
                  <NativeSelect
                    id="backtest-universe"
                    className={selectClass}
                    value={universe}
                    onChange={(event) => setUniverse(Number(event.target.value) as 50 | 100 | 500)}
                  >
                    {[50, 100, 500].map((value) => (
                      <option key={value} value={value}>
                        {value} empresas
                      </option>
                    ))}
                  </NativeSelect>
                </HelpField>
              </>
            ) : (
              <>
                <HelpField
                  id="backtest-mode"
                  label="Modo"
                  help="Muestra rápida para iterar; universo completo para un resultado citable (lento)."
                  className="text-xs font-medium"
                >
                  <NativeSelect
                    id="backtest-mode"
                    className={selectClass}
                    value={mode}
                    onChange={(event) => setMode(event.target.value as 'fast_dev' | 'validation')}
                  >
                    <option value="fast_dev">Muestra rápida</option>
                    <option value="validation">Universo completo</option>
                  </NativeSelect>
                </HelpField>
                {mode === 'fast_dev' && (
                  <HelpField
                    id="backtest-sample"
                    label="Empresas de muestra"
                    help="Empresas de la muestra rápida. Más empresas: más fiel y más lento."
                    className="text-xs font-medium"
                  >
                    <NativeSelect
                      id="backtest-sample"
                      className={selectClass}
                      value={sample}
                      onChange={(event) => setSample(Number(event.target.value) as 50 | 100 | 200)}
                    >
                      {[50, 100, 200].map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </NativeSelect>
                  </HelpField>
                )}
                <HelpField
                  id="backtest-capital"
                  label="Capital inicial ($)"
                  help="Dólares al empezar. Con comisión fija, un capital pequeño paga más en proporción."
                  className="text-xs font-medium"
                >
                  <Input
                    id="backtest-capital"
                    className="mt-1.5"
                    type="number"
                    min={1000}
                    step={1000}
                    value={capital}
                    onChange={(event) => setCapital(Number(event.target.value))}
                    required
                  />
                </HelpField>
                <HelpField
                  id="backtest-commission"
                  label="Comisión fija por operación ($)"
                  help="Dólares por cada compra o venta, como cobra el bróker calibrado."
                  className="text-xs font-medium"
                >
                  <Input
                    id="backtest-commission"
                    className="mt-1.5"
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    value={commission}
                    onChange={(event) => setCommission(Number(event.target.value))}
                    required
                  />
                </HelpField>
                <HelpField
                  id="backtest-spread"
                  label="Spread (pb)"
                  help="Puntos básicos (1 pb = 0,01 %) que empeoran cada precio de compra y venta."
                  className="text-xs font-medium"
                >
                  <Input
                    id="backtest-spread"
                    className="mt-1.5"
                    type="number"
                    min={0}
                    max={500}
                    step={0.5}
                    value={spread}
                    onChange={(event) => setSpread(Number(event.target.value))}
                    required
                  />
                </HelpField>
              </>
            )}
          </div>
        </AdvancedOptions>
        <p className="text-xs text-muted-foreground sm:col-span-2 lg:col-span-4">
          Fija el umbral de rotación y los costes antes de mirar el resultado. El universo completo
          puede tardar 20-30 minutos en rangos de varios años. Los datos deben estar preparados; el
          job no descarga fuentes.
        </p>
        <Button
          className="w-fit"
          type="submit"
          pending={run.isPending || ['queued', 'running'].includes(job.data?.status ?? '')}
          disabled={!researchAllowed}
        >
          {engine === 'backtest_v3_comparison' ? 'Comparar motores' : 'Ejecutar backtest'}
        </Button>
      </form>
      <PrepareData
        label="Preparar datos de todos los rebalanceos"
        start={start}
        end={end}
        preparation={{
          scope: 'backtest',
          months,
          max_symbols: engine === 'backtest_v1' ? universe : mode === 'fast_dev' ? sample : null,
        }}
      />
      {run.isError && <ErrorState error={run.error} retry={() => run.mutate()} />}
      {job.isError && <ErrorState error={job.error} retry={() => void job.refetch()} />}
      {job.data && (
        <section className="rounded-xl border bg-card p-5">
          <h3 className="font-semibold">Trabajo #{job.data.id.slice(0, 8)}</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            {job.data.phase} · {job.data.progress} % · {job.data.status}
          </p>
          {['queued', 'running'].includes(job.data.status) && (
            <Button
              className="mt-3"
              variant="outline"
              pending={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Solicitar cancelación
            </Button>
          )}
          {job.data.status === 'failed' && (
            <p className="mt-3 text-sm text-destructive">
              El backtest no terminó. Revisa la cobertura de datos locales del rango.
            </p>
          )}
        </section>
      )}
      {preview.isPending && job.data?.status === 'succeeded' && !comparing && <LoadingState />}
      {preview.isError && <ErrorState error={preview.error} retry={() => void preview.refetch()} />}
      {preview.data && <BacktestResult result={preview.data} />}
      {comparison.isPending && job.data?.status === 'succeeded' && comparing && <LoadingState />}
      {comparison.isError && (
        <ErrorState error={comparison.error} retry={() => void comparison.refetch()} />
      )}
      {comparison.data && <V3ComparisonResult result={comparison.data} />}
    </section>
  );
}

function BacktestResult({ result }: { result: BacktestPreview }) {
  const v2 = result.kind === 'backtest_v2';
  return (
    <section
      className="space-y-5 rounded-xl border bg-card p-5"
      aria-label="Resultado del backtest"
    >
      <div>
        <h3 className="text-xl font-semibold">
          {v2 ? 'Resultado V2' : 'Resultado V1'} · {dateText(result.start)} a {dateText(result.end)}
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Rebalanceo cada {result.months} meses · {result.top_n} empresas · umbral de rotación{' '}
          {num(result.rotation_hurdle_points, 1)} puntos ·{' '}
          {v2
            ? `${result.mode === 'validation' ? 'universo completo' : `muestra de ${result.max_symbols} (no citable)`} · ${num(result.commission_usd)} $ + ${num(result.spread_bps, 1)} pb`
            : `universo de ${result.universe_size} · ${num(result.cost_bps, 1)} pb por lado`}
        </p>
        {v2 && result.strict_result === false && (
          <p className="mt-2 text-sm text-destructive">
            Alguna posición dejó de cotizar sin evento terminal confirmado y se valoró a su último
            precio: el resultado no es estricto.
          </p>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Serie</th>
              <th>Acumulado</th>
              <th>Anualizado</th>
              <th>Sharpe</th>
              <th>Sortino</th>
              <th>Máx. drawdown</th>
            </tr>
          </thead>
          <tbody>
            {result.series.map((row) => (
              <tr key={row.name} className="border-b last:border-0">
                <td className="py-2">{SERIES[row.name]}</td>
                <td>{pct(row.total_return)}</td>
                <td>{pct(row.anualizado)}</td>
                <td>{num(row.sharpe)}</td>
                <td>{num(row.sortino)}</td>
                <td>{pct(row.max_drawdown)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Sharpe: exceso de retorno sobre la volatilidad. Sortino: solo penaliza la volatilidad a la
        baja. Drawdown: mayor caída desde un máximo.{' '}
        {v2
          ? 'En V2 se calculan sobre la curva diaria real.'
          : 'En V1 se calculan por periodos de rebalanceo; si el universo equiponderado tiene un Sharpe parecido, elegir las primeras no aporta tanto como sugiere el retorno.'}
      </p>
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Turnover medio" value={num(result.turnover_medio, 1) + ' %'} />
        {v2 && (
          <>
            <Stat label="Capital final" value={num(result.capital_final, 0) + ' $'} />
            <Stat label="Comisión total" value={num(result.comision_total, 0) + ' $'} />
            <Stat label="Coste total" value={num(result.coste_total, 0) + ' $'} />
            <Stat label="Calmar" value={num(result.calmar)} />
            <Stat label="Días de recuperación" value={num(result.recovery_days, 0)} />
            <Stat label="Beta frente al SPY" value={num(result.beta)} />
            <Stat label="Information Ratio" value={num(result.information_ratio)} />
            <Stat label="Captura al alza" value={pct(result.capture_upside, 0)} />
            <Stat label="Captura a la baja" value={pct(result.capture_downside, 0)} />
          </>
        )}
      </dl>
      <Suspense fallback={<p>Preparando gráfico…</p>}>
        <BacktestChart curve={result.curve} withUniverse={!v2} />
      </Suspense>
      <p className="text-xs text-muted-foreground">
        {v2
          ? 'Valor diario de la cartera y del SPY comprado y mantenido, en dólares.'
          : 'Capital acumulado partiendo de 1 en cada fecha de salida.'}
      </p>
      {result.skipped.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            {result.skipped.length} periodo(s) saltado(s) por falta de cobertura
          </summary>
          <ul className="mt-2 space-y-1 pl-5 text-muted-foreground">
            {result.skipped.map((row) => (
              <li key={row.fecha}>
                {row.fecha}: {row.motivo}
              </li>
            ))}
          </ul>
        </details>
      )}
      {result.exit_events.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            {result.exit_events.length} posición(es) liquidada(s) por baja de cotización
          </summary>
          <ul className="mt-2 space-y-1 pl-5 text-muted-foreground">
            {result.exit_events.map((row) => (
              <li key={row.symbol + row.fecha}>
                {row.fecha} · {row.symbol} · {row.estado}
                {row.estricto ? '' : ' · no estricto'}
              </li>
            ))}
          </ul>
        </details>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">
          {result.periods.length} rebalanceo(s)
        </summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-xs">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Desde</th>
                <th>Hasta</th>
                {v2 ? (
                  <>
                    <th>Compras</th>
                    <th>Ventas</th>
                    <th>Turnover</th>
                    <th>Coste</th>
                  </>
                ) : (
                  <>
                    <th>Candidatas</th>
                    <th>Retorno</th>
                    <th>SPY</th>
                    <th>Universo</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {result.periods.map((row) => (
                <tr key={row.fecha} className="border-b last:border-0 align-top">
                  <td className="py-2">{row.fecha}</td>
                  <td>{row.hasta}</td>
                  {v2 ? (
                    <>
                      <td>{row.bought || '—'}</td>
                      <td>{row.sold || '—'}</td>
                      <td>{num(row.turnover_pct, 1)} %</td>
                      <td>{num(row.coste_total)} $</td>
                    </>
                  ) : (
                    <>
                      <td>{row.candidatas}</td>
                      <td>{pct(row.retorno)}</td>
                      <td>{pct(row.spy)}</td>
                      <td>{pct(row.universo_ew)}</td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <a
        className="inline-block text-sm text-primary underline"
        href={'/api/v1/jobs/' + result.job_id + '/result'}
        download={'gabi-' + result.kind + '-' + result.job_id + '.json'}
      >
        Descargar backtest completo (periodos, curva, calidad de datos)
      </a>
      <p className="break-all text-xs text-muted-foreground">
        SHA-256: <Hash value={result.result_sha256} />
      </p>
      <BacktestDiagnostics jobId={result.job_id} v1={!v2} />
      {!v2 && (
        <BacktestFactors
          key={result.job_id}
          sourceJobId={result.job_id}
          periods={result.periods.length}
        />
      )}
      <BacktestRegister key={result.job_id} sourceJobId={result.job_id} />
    </section>
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
