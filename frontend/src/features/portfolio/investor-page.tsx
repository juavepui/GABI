import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type {
  Alternative,
  BenchmarkPerformance,
  BenchmarkSource,
  BenchmarkVehicle,
  InvestorProfileInput,
  InvestorProfileRevision,
  StressScenario,
} from '@/shared/api/generated/types.gen';
import {
  ApiError,
  getHoldingsBenchmark,
  getInvestorBenchmark,
  getInvestorProfile,
  getJobResult,
  saveInvestorProfile,
} from '@/shared/api/client';
import { useJob } from '@/shared/api/use-job';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Folded } from '@/shared/ui/folded';
import { PageHeader } from '@/shared/ui/page-header';
import { ProgressBar } from '@/shared/ui/progress-bar';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatMoney, formatPercent } from '@/shared/lib/format';

const PROFILE_KEY = ['portfolio', 'investor', 'profile'];
const BENCHMARK_KEY = ['portfolio', 'investor', 'benchmark'];
const eur = (value: number | null | undefined) =>
  formatMoney(value, { currency: 'EUR', digits: 0 });
const pct = (value: number | null | undefined) => formatPercent(value, { signed: true });
const EXCLUDED: Record<string, string> = {
  missing_price: 'sin precio en caché de su fecha',
  missing_fx: 'sin tipo de cambio en caché de su fecha',
  after_last_session: 'posterior al último precio de SPY',
};
const DEFAULTS: InvestorProfileInput = {
  initial_eur: 11000,
  monthly_eur: 700,
  horizon_months: 24,
  loss_tolerance: 0.2,
  capital_needed_by: null,
  tax_residence: null,
  commission_fixed_eur: 0,
  commission_pct: 0,
  fx_cost_pct: 0,
  min_order_eur: 0,
  fractional: true,
};

/** Percentages are typed in % and sent as fractions: the backend keeps the units. */
function profileBody(form: FormData): InvestorProfileInput {
  const number = (name: string) => Number(form.get(name) || 0);
  const text = (name: string) => String(form.get(name) ?? '').trim() || null;
  return {
    initial_eur: number('initial_eur'),
    monthly_eur: number('monthly_eur'),
    horizon_months: number('horizon_months'),
    loss_tolerance: number('loss_tolerance') / 100,
    capital_needed_by: text('capital_needed_by'),
    tax_residence: text('tax_residence'),
    commission_fixed_eur: number('commission_fixed_eur'),
    commission_pct: number('commission_pct') / 100,
    fx_cost_pct: number('fx_cost_pct') / 100,
    min_order_eur: number('min_order_eur'),
    fractional: form.get('fractional') === 'on',
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="text-sm font-medium">
      {label}
      {children}
      {hint && <span className="mt-1 block text-xs font-normal text-muted-foreground">{hint}</span>}
    </label>
  );
}

type SaveProfile = UseMutationResult<InvestorProfileRevision, Error, InvestorProfileInput>;

/** The mutation lives in the page: a new revision remounts the form, but its confirmation stays. */
function ProfileForm({ profile, save }: { profile: InvestorProfileInput; save: SaveProfile }) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(profileBody(new FormData(event.currentTarget)));
  }
  const percent = (value: number | undefined) => String(Math.round((value ?? 0) * 10000) / 100);
  return (
    <form
      onSubmit={submit}
      aria-label="Perfil de inversor"
      className="rounded-xl border bg-card p-5"
    >
      <h2 className="text-xl font-semibold">Tu perfil</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Field label="Capital inicial (€)">
          <Input
            className="mt-1.5"
            name="initial_eur"
            type="number"
            min={0}
            step="0.01"
            defaultValue={profile.initial_eur}
            required
          />
        </Field>
        <Field label="Aportación mensual (€)">
          <Input
            className="mt-1.5"
            name="monthly_eur"
            type="number"
            min={0}
            step="0.01"
            defaultValue={profile.monthly_eur}
          />
        </Field>
        <Field label="Horizonte de evaluación (meses)" hint="Plazo para juzgar a GABI.">
          <Input
            className="mt-1.5"
            name="horizon_months"
            type="number"
            min={1}
            max={600}
            defaultValue={profile.horizon_months}
            required
          />
        </Field>
        <Field
          label="Tolerancia de pérdida (%)"
          hint="Umbral de revisión: no es una garantía ni vende por sí solo."
        >
          <Input
            className="mt-1.5"
            name="loss_tolerance"
            type="number"
            min={1}
            max={99}
            step="0.1"
            defaultValue={percent(profile.loss_tolerance)}
            required
          />
        </Field>
        <Field label="¿Cuándo necesitarás el dinero?" hint="Opcional; distinto del horizonte.">
          <Input
            className="mt-1.5"
            name="capital_needed_by"
            type="date"
            defaultValue={profile.capital_needed_by ?? ''}
          />
        </Field>
        <Field label="Residencia fiscal (ISO)" hint="Sin confirmar no se aplica fiscalidad.">
          <Input
            className="mt-1.5"
            name="tax_residence"
            maxLength={2}
            defaultValue={profile.tax_residence ?? ''}
          />
        </Field>
      </div>
      <h3 className="mt-6 font-semibold">Costes de tu bróker</h3>
      <p className="text-xs text-muted-foreground">Se aplican igual a la cartera y al benchmark.</p>
      <div className="mt-3 grid gap-4 sm:grid-cols-4">
        <Field label="Comisión fija (€)">
          <Input
            className="mt-1.5"
            name="commission_fixed_eur"
            type="number"
            min={0}
            step="0.01"
            defaultValue={profile.commission_fixed_eur}
          />
        </Field>
        <Field label="Comisión (%)">
          <Input
            className="mt-1.5"
            name="commission_pct"
            type="number"
            min={0}
            max={9.99}
            step="0.01"
            defaultValue={percent(profile.commission_pct)}
          />
        </Field>
        <Field label="Conversión de divisa (%)">
          <Input
            className="mt-1.5"
            name="fx_cost_pct"
            type="number"
            min={0}
            max={9.99}
            step="0.01"
            defaultValue={percent(profile.fx_cost_pct)}
          />
        </Field>
        <Field label="Importe mínimo por orden (€)">
          <Input
            className="mt-1.5"
            name="min_order_eur"
            type="number"
            min={0}
            step="0.01"
            defaultValue={profile.min_order_eur}
          />
        </Field>
      </div>
      <label className="mt-4 flex items-center gap-2 text-sm">
        <input type="checkbox" name="fractional" defaultChecked={profile.fractional ?? true} />
        Mi bróker permite comprar fracciones de acción
      </label>
      <Button className="mt-4" type="submit" pending={save.isPending}>
        Guardar perfil
      </Button>
      {save.isSuccess && (
        <p role="status" className="mt-2 text-sm">
          Guardado como revisión {save.data.revision}. Las anteriores se conservan.
        </p>
      )}
      {save.isError && <ErrorState error={save.error} retry={() => save.reset()} />}
    </form>
  );
}

type PricesResult = { symbols: string[]; updated: number; failed: Record<string, string> };

/** The explicit download: a GET never fetches prices. */
function BenchmarkPrices() {
  const queryClient = useQueryClient();
  const { start, job } = useJob('benchmark-prices');
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  const result = useQuery({
    queryKey: ['job', job.data?.id, 'result'],
    queryFn: ({ signal }) => getJobResult(job.data!.id, signal) as Promise<PricesResult>,
    enabled: job.data?.status === 'succeeded',
  });
  const done = result.data != null;
  useEffect(() => {
    if (done) void queryClient.invalidateQueries({ queryKey: ['portfolio', 'investor'] });
  }, [done, queryClient]);
  const failed = Object.keys(result.data?.failed ?? {});
  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        pending={running}
        onClick={() => start.mutate({ kind: 'benchmark_prices' })}
      >
        Actualizar benchmark
      </Button>
      <p className="text-xs text-muted-foreground">
        Descarga de Yahoo Finance: SPY, el cambio USDEUR=X, el índice ^SP500TR y el ETF SXR8.DE.
      </p>
      {start.isError && <ErrorState error={start.error} retry={() => start.reset()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <ProgressBar value={job.data.progress} phase={job.data.phase} status={job.data.status} />
      )}
      {result.data && (
        <p role="status" className="text-sm">
          Actualizados {result.data.updated} símbolos; fallos: {failed.length}
          {failed.length > 0 && ' (' + failed.join(', ') + ')'}.
        </p>
      )}
    </div>
  );
}

function Cards({ items }: { items: [string, string, string][] }) {
  return (
    <dl className="mt-4 grid gap-3 sm:grid-cols-4">
      {items.map(([label, value, note]) => (
        <div key={label} className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>
          <dd className="text-xs text-muted-foreground">{note}</dd>
        </div>
      ))}
    </dl>
  );
}

function performanceCards(performance: BenchmarkPerformance): [string, string, string][] {
  return [
    ['Aportado', eur(performance.contributed_eur), 'Costes: ' + eur(performance.costs_eur)],
    ['Valor final', eur(performance.final_value_eur), 'Cierre del ' + (performance.end ?? '—')],
    ['TWR', pct(performance.twr), 'Habilidad: no depende de cuándo aportas'],
    ['XIRR', pct(performance.xirr), 'Tu experiencia, anualizada'],
    [
      'Caída máxima',
      pct(performance.max_drawdown),
      'Por participación: el dinero nuevo no la oculta',
    ],
    [
      'Peor momento sobre lo aportado',
      pct(performance.max_loss_on_contributions),
      eur(performance.max_euros_lost) + ' en euros',
    ],
    [
      'En riesgo con tu tolerancia',
      eur(performance.euros_at_risk_at_tolerance),
      'Sobre el valor actual',
    ],
    [
      'Umbral de revisión',
      performance.review_threshold_reached_on ? 'Alcanzado' : 'No alcanzado',
      performance.review_threshold_reached_on
        ? 'El ' + performance.review_threshold_reached_on + '; revisar, no vender por sí solo'
        : 'La caída nunca llegó a tu tolerancia',
    ],
  ];
}

function SourceNote({ source }: { source: BenchmarkSource }) {
  return (
    <p className="mt-3 text-xs text-muted-foreground">
      {source.vehicle} Precios del {source.first_price} al {source.last_price}; cambio {source.fx}{' '}
      del {source.first_fx} al {source.last_fx}. Fuente: {source.provider}.
    </p>
  );
}

function MissingPrices({ error, retry }: { error: Error; retry: () => void }) {
  if (error instanceof ApiError && error.code === 'benchmark_prices_missing') {
    return <p className="mt-3 text-sm">{error.message}</p>;
  }
  return <ErrorState error={error} retry={retry} />;
}

function PlanBenchmark() {
  const [start, setStart] = useState<string | null>(null);
  const benchmark = useQuery({
    queryKey: [...BENCHMARK_KEY, start],
    queryFn: ({ signal }) => getInvestorBenchmark(start, signal),
    retry: false,
  });
  const data = benchmark.data;
  return (
    <section aria-label="Tu plan en el S&P 500" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Tu plan invertido en el S&P 500</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Qué habría pasado con tu capital inicial y tus aportaciones mensuales comprando SPY con los
        costes de tu bróker. No es una previsión.
      </p>
      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          const value = String(new FormData(event.currentTarget).get('start') ?? '');
          setStart(value || null);
        }}
      >
        <Field label="Desde">
          <Input
            className="mt-1.5"
            name="start"
            type="date"
            key={data?.start}
            defaultValue={data?.start}
          />
        </Field>
        <Button type="submit" variant="outline" pending={benchmark.isFetching}>
          Simular
        </Button>
      </form>
      <div className="mt-3">
        <BenchmarkPrices />
      </div>
      {benchmark.isPending && <LoadingState />}
      {benchmark.isError && (
        <MissingPrices error={benchmark.error} retry={() => void benchmark.refetch()} />
      )}
      {data && (
        <>
          {data.capital_need_before_horizon && (
            <p role="alert" className="mt-3 text-sm font-medium text-destructive">
              Necesitas el dinero antes de terminar el horizonte: aclara ese plazo antes de exponer
              ese capital a renta variable.
            </p>
          )}
          <Cards items={performanceCards(data.performance)} />
          {data.pending.length > 0 && (
            <p className="mt-3 text-sm">
              Aportaciones sin precio todavía: {data.pending.map((row) => row.date).join(', ')}.
            </p>
          )}
          <SourceNote source={data.source} />
          <Vehicles reference={data.performance} vehicles={data.vehicles} />
          <Scenarios
            rows={data.scenarios}
            note="Todo el plan está expuesto al dólar: es el S&P 500."
          />
        </>
      )}
    </section>
  );
}

/** The same contributions in the theoretical index and in a vehicle an EU investor can buy. */
function Vehicles({
  reference,
  vehicles,
}: {
  reference: BenchmarkPerformance;
  vehicles: BenchmarkVehicle[];
}) {
  const rows: [string, string, BenchmarkPerformance | null | undefined][] = [
    ['SPY (referencia de arriba)', 'Cierre ajustado con dividendos brutos', reference],
    ...vehicles.map((row): [string, string, BenchmarkPerformance | null | undefined] => [
      row.symbol + (row.theoretical ? ' · teórico' : ' · invertible'),
      row.status === 'ok' ? row.label : 'Sin precios en caché: pulsa «Actualizar benchmark».',
      row.performance,
    ]),
  ];
  return (
    <div className="mt-5 overflow-x-auto">
      <h3 className="font-semibold">Índice teórico frente a vehículo invertible</h3>
      <table className="mt-2 w-full text-left text-xs sm:text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="pb-2">Vehículo</th>
            <th className="pb-2">Valor final</th>
            <th className="pb-2">Costes</th>
            <th className="pb-2">TWR</th>
            <th className="pb-2">XIRR</th>
            <th className="pb-2">Caída máxima</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, note, performance]) => (
            <tr key={name} className="border-b align-top last:border-0">
              <td className="py-2">
                <span className="font-medium">{name}</span>
                <span className="block max-w-sm text-xs text-muted-foreground">{note}</span>
              </td>
              <td className="py-2 tabular-nums">{eur(performance?.final_value_eur)}</td>
              <td className="py-2 tabular-nums">{eur(performance?.costs_eur)}</td>
              <td className="py-2 tabular-nums">{pct(performance?.twr)}</td>
              <td className="py-2 tabular-nums">{pct(performance?.xirr)}</td>
              <td className="py-2 tabular-nums">{pct(performance?.max_drawdown)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Declared shocks, not forecasts: crossing the tolerance means reviewing the plan, never selling by itself. */
function Scenarios({ rows, note }: { rows: StressScenario[]; note: string }) {
  if (!rows.length) return null;
  return (
    <div className="mt-5 overflow-x-auto">
      <h3 className="font-semibold">Escenarios de estrés</h3>
      <p className="text-xs text-muted-foreground">
        Efecto inmediato sobre el valor actual. No son previsiones. {note}
      </p>
      <table className="mt-2 w-full text-left text-xs sm:text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="pb-2">Escenario</th>
            <th className="pb-2">Efecto</th>
            <th className="pb-2">En euros</th>
            <th className="pb-2">Tu tolerancia</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b last:border-0">
              <td className="py-2">{row.label}</td>
              <td className="py-2 tabular-nums">{pct(row.change)}</td>
              <td className="py-2 tabular-nums">{eur(row.change_eur)}</td>
              <td className="py-2">{row.exceeds_tolerance ? 'Superada: revisar el plan' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A range of splits between the active portfolio and the index; GABI does not pick one. */
function Alternatives({ rows }: { rows: Alternative[] }) {
  return (
    <div className="mt-5 overflow-x-auto">
      <h3 className="font-semibold">Activa, mixta e indexada con las mismas compras</h3>
      <p className="text-xs text-muted-foreground">
        Cada compra repartida entre tu cartera y SPY. Es un rango para comparar, no una
        recomendación de pesos.
      </p>
      <table className="mt-2 w-full text-left text-xs sm:text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="pb-2">Alternativa</th>
            <th className="pb-2">Valor final</th>
            <th className="pb-2">TWR</th>
            <th className="pb-2">XIRR</th>
            <th className="pb-2">Caída máxima</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.index_weight} className="border-b last:border-0">
              <td className="py-2">{row.label}</td>
              <td className="py-2 tabular-nums">{eur(row.performance.final_value_eur)}</td>
              <td className="py-2 tabular-nums">{pct(row.performance.twr)}</td>
              <td className="py-2 tabular-nums">{pct(row.performance.xirr)}</td>
              <td className="py-2 tabular-nums">{pct(row.performance.max_drawdown)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HoldingsComparison() {
  const comparison = useQuery({
    queryKey: [...BENCHMARK_KEY, 'holdings'],
    queryFn: ({ signal }) => getHoldingsBenchmark(signal),
    retry: false,
  });
  const data = comparison.data;
  const noHoldings =
    comparison.error instanceof ApiError && comparison.error.code === 'no_holdings';
  return (
    <section aria-label="Mi cartera frente a SPY" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Mi cartera frente a SPY con los mismos euros</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Cada compra de{' '}
        <Link className="text-primary underline" to="/cartera/mi-cartera">
          Mi cartera
        </Link>{' '}
        compra también SPY el mismo día y por el mismo importe. Ambas con dividendos reinvertidos
        (cierre ajustado).
      </p>
      {comparison.isPending && <LoadingState />}
      {noHoldings && <p className="mt-3 text-sm">Todavía no has registrado compras.</p>}
      {comparison.isError && !noHoldings && (
        <MissingPrices error={comparison.error} retry={() => void comparison.refetch()} />
      )}
      {data && (
        <>
          <Cards
            items={[
              [
                'Diferencia de riqueza',
                eur(data.comparison.wealth_difference_eur),
                'Mi cartera menos SPY',
              ],
              ['Diferencia de TWR', pct(data.comparison.twr_difference), 'Habilidad'],
              ['Diferencia de XIRR', pct(data.comparison.xirr_difference), 'Experiencia'],
              [
                'Diferencia de caída máxima',
                pct(data.comparison.max_drawdown_difference),
                'Positiva: mi cartera cayó menos',
              ],
            ]}
          />
          <h3 className="mt-5 font-semibold">Mi cartera</h3>
          <Cards items={performanceCards(data.portfolio)} />
          <h3 className="mt-5 font-semibold">SPY con los mismos euros</h3>
          <Cards items={performanceCards(data.benchmark)} />
          {data.excluded.length > 0 && (
            <p className="mt-3 text-sm">
              Compras excluidas de ambos lados:{' '}
              {data.excluded
                .map(
                  (row) =>
                    `${row.symbol} del ${row.purchase_date} (${EXCLUDED[row.reason] ?? row.reason})`,
                )
                .join('; ')}
              .
            </p>
          )}
          {data.incomplete_sessions > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              Sesiones sin precio de alguna posición omitidas: {data.incomplete_sessions}.
            </p>
          )}
          <Alternatives rows={data.alternatives} />
          <Scenarios
            rows={data.scenarios}
            note={
              'Exposición al dólar aproximada por la divisa de cotización: ' +
              formatPercent(data.usd_share, { digits: 0 }) +
              ' del valor actual.'
            }
          />
          <SourceNote source={data.source} />
        </>
      )}
    </section>
  );
}

export function InvestorPage() {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: saveInvestorProfile,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['portfolio', 'investor'] }),
  });
  const profile = useQuery({
    queryKey: PROFILE_KEY,
    queryFn: ({ signal }) => getInvestorProfile(signal),
  });
  const current = profile.data?.current;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cartera / Perfil"
        title="Perfil y benchmark"
        description={
          <>
            Tu capital, tus aportaciones y tu tolerancia, y cómo les habría ido en el S&P 500 en
            euros. No es una promesa de superar al índice.
          </>
        }
        guide={
          <p>
            La TWR mide la habilidad sin depender de cuándo aportas; la XIRR y la riqueza final
            miden tu experiencia. La caída se calcula por participación para que el dinero nuevo no
            la oculte. Los datos salen de la caché local; solo «Actualizar benchmark» descarga.
          </p>
        }
      />
      {profile.isPending && <LoadingState />}
      {profile.isError && <ErrorState error={profile.error} retry={() => void profile.refetch()} />}
      {profile.data && (
        <>
          <ProfileForm
            key={current?.revision ?? 0}
            profile={current ? current.profile : DEFAULTS}
            save={save}
          />
          {current ? (
            <>
              <PlanBenchmark />
              <HoldingsComparison />
            </>
          ) : (
            <p className="text-sm">
              Guarda tu perfil para ver tu plan en el S&P 500. Los valores propuestos son
              orientativos: cámbialos por los tuyos.
            </p>
          )}
          {profile.data.revisions.length > 1 && (
            <Folded title={`Revisiones del perfil (${profile.data.revisions.length})`}>
              <ul className="space-y-1 text-sm">
                {profile.data.revisions.map((row) => (
                  <li key={row.revision}>
                    Revisión {row.revision} · {row.created_at.slice(0, 10)} ·{' '}
                    {eur(row.profile.initial_eur)} + {eur(row.profile.monthly_eur)}/mes ·{' '}
                    {row.profile.horizon_months} meses · tolerancia{' '}
                    {formatPercent(row.profile.loss_tolerance)}
                  </li>
                ))}
              </ul>
            </Folded>
          )}
        </>
      )}
    </div>
  );
}
