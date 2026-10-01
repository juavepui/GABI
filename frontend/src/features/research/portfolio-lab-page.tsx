import { lazy, Suspense, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getModel, getPortfolioLab } from '@/shared/api/client';
import type { PortfolioLabPreview } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { JobStatus } from './experiment-jobs';
import { TailRiskTable } from './tail-risk-table';
import { useJob } from '@/shared/api/use-job';

const WealthChart = lazy(() =>
  import('./backtest-factor-charts').then((module) => ({ default: module.WealthChart })),
);

const SCHEMES = [
  ['equal_weight', 'Equal Weight'],
  ['inverse_vol', 'Inverse Volatility'],
  ['min_variance', 'Minimum Variance'],
  ['score_weighted', 'Score-weighted'],
  ['score_constrained', 'Score + risk constrained'],
  ['risk_parity', 'Risk Parity'],
] as const;
type Scheme = (typeof SCHEMES)[number][0];

const pct = (value: number | null | undefined, digits = 1) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(value * 100) + ' %';
const num = (value: number | null | undefined, digits = 2) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(value);
const usd = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }).format(value) + ' $';

function Result({ data }: { data: PortfolioLabPreview }) {
  const [riskScheme, setRiskScheme] = useState(data.schemes[0]?.id ?? '');
  const selected = data.schemes.find((scheme) => scheme.id === riskScheme);
  const risk = selected
    ? Object.keys(selected.contribution_to_risk)
        .map((symbol) => ({
          symbol,
          weight: selected.last_weights[symbol] ?? null,
          risk: selected.contribution_to_risk[symbol] ?? null,
        }))
        .sort((a, b) => (b.risk ?? 0) - (a.risk ?? 0))
    : [];
  const top3 = risk.slice(0, 3);
  const series = [...data.schemes.map((scheme) => scheme.id), 'spy'];
  const labels = {
    ...Object.fromEntries(data.schemes.map((scheme) => [scheme.id, scheme.label])),
    spy: 'SPY (buy & hold)',
  };
  const points = data.curve.map((row) => ({ ...row, date: String(row.fecha) }));
  const scenarios = Object.keys(data.scenario_labels);
  return (
    <section className="space-y-6" role="region" aria-label="Resultado de Portfolio Lab">
      <p className="text-sm text-muted-foreground">
        {data.start} a {data.end} ·{' '}
        {data.mode === 'validation'
          ? 'Universo completo'
          : `Muestra de ${data.options.max_symbols} empresas`}{' '}
        · ensayo retrospectivo, no validación independiente.
      </p>
      {data.skipped.length > 0 && (
        <details className="rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer">
            {data.skipped.length} periodo(s) saltado(s) por falta de cobertura
          </summary>
          <ul className="mt-2 space-y-1 text-xs">
            {data.skipped.map((row) => (
              <li key={row.fecha}>
                {row.fecha}: {row.motivo}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div>
        <h2 className="text-lg font-semibold">Comparativa por esquema</h2>
        <div className="mt-2 overflow-x-auto">
          <table
            className="w-full min-w-[900px] text-left text-xs"
            aria-label="Comparativa por esquema"
          >
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Esquema</th>
                <th>Retorno anualizado</th>
                <th>Volatilidad anualizada</th>
                <th>Sharpe</th>
                <th>Máx. drawdown</th>
                <th>Turnover medio (%)</th>
                <th>Coste total</th>
                <th>HHI</th>
                <th>Top-3 contribución al riesgo</th>
                <th>Tracking error vs SPY</th>
              </tr>
            </thead>
            <tbody>
              {data.schemes.map((scheme) => (
                <tr key={scheme.id} className="border-b last:border-0">
                  <td className="py-1.5">{scheme.label}</td>
                  <td>{pct(scheme.daily.anualizado)}</td>
                  <td>{pct(scheme.daily.vol_anualizada)}</td>
                  <td>{num(scheme.daily.sharpe)}</td>
                  <td>{pct(scheme.daily.max_drawdown)}</td>
                  <td>{num(scheme.turnover_medio, 1)}</td>
                  <td>{usd(scheme.comision_total)}</td>
                  <td>{num(scheme.hhi, 3)}</td>
                  <td>{pct(scheme.top3_contribution_to_risk)}</td>
                  <td>{pct(scheme.tracking_error)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          HHI (Herfindahl-Hirschman) = Σwᵢ²: 1/N es el mínimo con N posiciones equiponderadas y 1 es
          todo en una sola. Top-3 contribución al riesgo = fracción de la varianza total de la
          cartera (no del capital) que explican las 3 posiciones con más riesgo, con los pesos del
          último rebalanceo.
        </p>
      </div>
      <div>
        <h2 className="text-lg font-semibold">Curvas de capital</h2>
        <Suspense fallback={<p>Preparando gráfico…</p>}>
          <WealthChart points={points} series={series} labels={labels} />
        </Suspense>
        <details className="mt-3 rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer font-medium">
            Riesgo de cola · comparar esquemas y SPY
          </summary>
          <TailRiskTable
            horizon={data.tail.horizon ?? ''}
            series={data.tail.series}
            message={data.tail.message}
          />
        </details>
        <a
          className="mt-2 inline-block text-sm text-primary underline"
          href={'/api/v1/jobs/' + data.job_id + '/result'}
          download={'gabi-portfolio-lab-' + data.job_id + '.json'}
        >
          Descargar resultado completo (curvas, periodos, pesos y escenarios)
        </a>
      </div>
      <div>
        <h2 className="text-lg font-semibold">Concentración del riesgo (último rebalanceo)</h2>
        <label className="mt-2 grid w-fit gap-1 text-sm">
          Esquema
          <NativeSelect value={riskScheme} onChange={(event) => setRiskScheme(event.target.value)}>
            {data.schemes.map((scheme) => (
              <NativeSelectOption key={scheme.id} value={scheme.id}>
                {scheme.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        {risk.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            Sin datos de covarianza suficientes para este esquema en el último rebalanceo.
          </p>
        ) : (
          <>
            <table className="mt-2 text-left text-xs" aria-label="Concentración del riesgo">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2 pr-6">Empresa</th>
                  <th className="pr-6">Peso en $</th>
                  <th>Contribución al riesgo</th>
                </tr>
              </thead>
              <tbody>
                {risk.map((row) => (
                  <tr key={row.symbol} className="border-b last:border-0">
                    <td className="py-1.5 pr-6">{row.symbol}</td>
                    <td className="pr-6">{pct(row.weight)}</td>
                    <td>{pct(row.risk)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-sm">
              Ejemplo concreto: <strong>{top3.map((row) => row.symbol).join(', ')}</strong> juntas
              representan un{' '}
              <strong>{pct(top3.reduce((sum, row) => sum + (row.risk ?? 0), 0))}</strong> del riesgo
              total de esta cartera con {selected?.label}.
            </p>
          </>
        )}
      </div>
      <div>
        <h2 className="text-lg font-semibold">Stress tests</h2>
        <p className="mt-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
          No son pronósticos: son shocks arbitrarios con supuestos simples, aplicados a los pesos
          del último rebalanceo de cada esquema. Los escenarios con base real usan beta y sector de
          precios reales; los marcados como heurística usan una tabla por sector sin calibrar y son
          solo orientativos.
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-xs" aria-label="Stress tests">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Esquema</th>
                {scenarios.map((scenario) => (
                  <th key={scenario}>
                    {data.scenario_labels[scenario]}{' '}
                    {data.scenario_ground[scenario] === 'real' ? '(base real)' : '(heurística)'}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.schemes.map((scheme) => (
                <tr key={scheme.id} className="border-b last:border-0">
                  <td className="py-1.5">{scheme.label}</td>
                  {scenarios.map((scenario) => {
                    const outcome = data.scenarios[scheme.id]?.[scenario];
                    return (
                      <td key={scenario}>
                        {outcome == null
                          ? '—'
                          : pct(
                              outcome.tipo === 'volatilidad'
                                ? outcome.vol_escenario
                                : outcome.impacto_pct,
                            )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          «Volatilidad ×2» muestra la volatilidad anualizada resultante, no un retorno.
        </p>
      </div>
    </section>
  );
}

export function PortfolioLabPage() {
  const model = useQuery({ queryKey: ['model'], queryFn: ({ signal }) => getModel(signal) });
  const [start, setStart] = useState('2019-01-02');
  const [end, setEnd] = useState('2024-01-02');
  const [months, setMonths] = useState<1 | 3 | 6 | 12>(3);
  const [topN, setTopN] = useState(20);
  const [capital, setCapital] = useState(100000);
  const [schemes, setSchemes] = useState<Scheme[]>(SCHEMES.map(([id]) => id));
  const [mode, setMode] = useState<'fast_dev' | 'validation'>('fast_dev');
  const [sample, setSample] = useState<50 | 100 | 200>(100);
  const state = useJob('portfolio-lab');
  const preview = useQuery({
    queryKey: ['research', 'portfolio-lab', state.jobId],
    queryFn: ({ signal }) => getPortfolioLab(state.jobId!, signal),
    enabled: state.jobId != null && state.job.data?.status === 'succeeded',
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    state.setJobId(null);
    state.start.mutate({
      kind: 'portfolio_lab',
      start,
      end,
      portfolio_options: {
        months,
        top_n: topN,
        initial_capital: capital,
        schemes,
        mode,
        max_symbols: mode === 'fast_dev' ? sample : null,
      },
    });
  }

  return (
    <div className="space-y-6">
      <header>
        <Link className="text-sm text-primary" to="/investigacion">
          ← Investigación
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Portfolio Lab</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Con las mismas candidatas de cada rebalanceo, compara seis formas de repartir el capital,
          sin declarar ganador de antemano. Fíjate en el HHI y en la contribución al riesgo de las 3
          mayores posiciones, no solo en el número de posiciones: 20 empresas no significan 20
          fuentes de riesgo.
        </p>
      </header>
      <details className="rounded-xl border bg-card p-4 text-sm">
        <summary className="cursor-pointer font-medium">Qué significa cada esquema</summary>
        <ul className="mt-2 space-y-1">
          <li>
            <strong>Equal Weight</strong>: mismo % de capital en cada posición; el caso base.
          </li>
          <li>
            <strong>Inverse Volatility</strong>: más peso a las acciones menos volátiles (no mira
            correlaciones).
          </li>
          <li>
            <strong>Minimum Variance</strong>: los pesos que minimizan la volatilidad total con la
            covarianza, sin límites de posición ni sector.
          </li>
          <li>
            <strong>Score-weighted</strong>: peso proporcional al composite score.
          </li>
          <li>
            <strong>Score + risk constrained</strong>: media-varianza con límites de posición y
            sector en el optimizador; si son inviables en un periodo, usa Score-weighted.
          </li>
          <li>
            <strong>Risk Parity</strong>: cada posición aporta la misma fracción del riesgo total.
          </li>
        </ul>
      </details>
      <form
        className="grid gap-3 rounded-xl border bg-card p-5 text-sm sm:grid-cols-3"
        aria-label="Ejecutar Portfolio Lab"
        onSubmit={submit}
      >
        <label className="grid gap-1">
          Inicio
          <Input
            type="date"
            min="2010-01-01"
            max="2025-07-02"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </label>
        <label className="grid gap-1">
          Fin
          <Input
            type="date"
            min="2010-01-01"
            max="2025-07-02"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </label>
        <label className="grid gap-1">
          Rebalanceo
          <NativeSelect
            value={String(months)}
            onChange={(event) => setMonths(Number(event.target.value) as 1 | 3 | 6 | 12)}
          >
            {[1, 3, 6, 12].map((value) => (
              <NativeSelectOption key={value} value={String(value)}>
                Cada {value} meses
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <label className="grid gap-1">
          Nº de posiciones
          <Input
            type="number"
            min={2}
            max={50}
            value={String(topN)}
            onChange={(event) => setTopN(Number(event.target.value))}
          />
        </label>
        <label className="grid gap-1">
          Capital inicial ($)
          <Input
            type="number"
            min={1000}
            max={10000000}
            step={1000}
            value={String(capital)}
            onChange={(event) => setCapital(Number(event.target.value))}
          />
        </label>
        <label className="grid gap-1">
          Modo
          <NativeSelect
            value={mode}
            onChange={(event) => setMode(event.target.value as 'fast_dev' | 'validation')}
          >
            <NativeSelectOption value="fast_dev">Desarrollo rápido (muestra)</NativeSelectOption>
            <NativeSelectOption value="validation">
              Validación (universo completo, lento)
            </NativeSelectOption>
          </NativeSelect>
        </label>
        {mode === 'fast_dev' && (
          <label className="grid gap-1">
            Tamaño de la muestra
            <NativeSelect
              value={String(sample)}
              onChange={(event) => setSample(Number(event.target.value) as 50 | 100 | 200)}
            >
              {[50, 100, 200].map((value) => (
                <NativeSelectOption key={value} value={String(value)}>
                  {value} empresas
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
        )}
        <fieldset className="grid gap-1 sm:col-span-3">
          <legend className="mb-1">Esquemas a comparar</legend>
          <div className="flex flex-wrap gap-4">
            {SCHEMES.map(([id, label]) => (
              <label key={id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={schemes.includes(id)}
                  onChange={(event) =>
                    setSchemes((current) =>
                      event.target.checked
                        ? SCHEMES.map(([scheme]) => scheme).filter(
                            (scheme) => scheme === id || current.includes(scheme),
                          )
                        : current.filter((scheme) => scheme !== id),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <p className="text-xs text-muted-foreground sm:col-span-3">
          Solo el histórico observado del S&amp;P 500 (2010-01-01 a 2025-07-02). Validación usa el
          universo completo de cada fecha y es el único modo citable; puede tardar bastante.
        </p>
        <Button
          type="submit"
          className="w-fit"
          disabled={
            schemes.length === 0 || state.start.isPending || model.data?.mode !== 'RESEARCH'
          }
        >
          Ejecutar Portfolio Lab
        </Button>
        {model.data && model.data.mode !== 'RESEARCH' && (
          <p className="text-sm text-muted-foreground sm:col-span-3">
            Portfolio Lab requiere el modo Research (Administración → Activar Research).
          </p>
        )}
      </form>
      <JobStatus state={state} />
      {preview.isPending && state.job.data?.status === 'succeeded' && <LoadingState />}
      {preview.isError && <ErrorState error={preview.error} retry={() => void preview.refetch()} />}
      {preview.data && <Result data={preview.data} />}
    </div>
  );
}
