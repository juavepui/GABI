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
        <Field
          label="¿Cuántos meses le das a GABI? (horizonte)"
          hint="Tiempo que esperarás antes de juzgar si funciona. En bolsa, menos de 3–5 años es poco."
        >
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
          label="¿Qué caída aguantarías sin vender? (%)"
          hint="Si tu dinero cae más, GABI te avisará para que revises tu plan. No vende ni te protege por sí solo."
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
        <Field
          label="¿Cuándo necesitarás este dinero?"
          hint="Opcional. Si lo necesitas pronto, la bolsa puede no ser buen sitio para él."
        >
          <Input
            className="mt-1.5"
            name="capital_needed_by"
            type="date"
            defaultValue={profile.capital_needed_by ?? ''}
          />
        </Field>
        <Field
          label="País donde pagas impuestos (código de 2 letras, p. ej. ES)"
          hint="Si lo dejas vacío no se calculan impuestos."
        >
          <Input
            className="mt-1.5"
            name="tax_residence"
            maxLength={2}
            defaultValue={profile.tax_residence ?? ''}
          />
        </Field>
      </div>
      <h3 className="mt-6 font-semibold">Costes de tu bróker</h3>
      <p className="text-xs text-muted-foreground">
        Se aplican igual a tu cartera y al índice de referencia, para que la comparación sea justa.
      </p>
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
        <Field label="Comisión por cambiar euros a dólares (%)">
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
        <Field label="Importe mínimo por compra (€)">
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
        Actualizar precios del índice
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
    ['Valor al final', eur(performance.final_value_eur), 'Al cierre del ' + (performance.end ?? '—')],
    ['Rentabilidad de la inversión (TWR)', pct(performance.twr), 'Cuánto rindió, sin importar cuándo metiste dinero'],
    ['Tu rentabilidad anual (XIRR)', pct(performance.xirr), 'Lo que ganaste tú al año, contando cuándo aportaste'],
    [
      'Mayor caída',
      pct(performance.max_drawdown),
      'Medida sin que el dinero nuevo la disimule',
    ],
    [
      'Peor momento sobre lo aportado',
      pct(performance.max_loss_on_contributions),
      eur(performance.max_euros_lost) + ' en euros',
    ],
    [
      'Lo que perderías con la caída que aceptas',
      eur(performance.euros_at_risk_at_tolerance),
      'Sobre el valor actual',
    ],
    [
      '¿Se llegó a tu caída máxima?',
      performance.review_threshold_reached_on ? 'Sí' : 'No',
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
      <h2 className="text-xl font-semibold">¿Y si lo hubieras metido todo en el S&P 500?</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Qué habría pasado con tu dinero inicial y tus aportaciones de cada mes si los hubieras
        invertido en el S&amp;P 500 (con el fondo SPY), con las comisiones de tu bróker. Es lo que
        pasó en el pasado, no una previsión.
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
              Necesitas el dinero antes de que acabe el plazo que le das a GABI. La bolsa puede caer
              justo cuando lo necesites: piénsalo antes de invertir ese dinero en acciones.
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
    ['SPY (el de arriba)', 'Con los dividendos reinvertidos, antes de impuestos', reference],
    ...vehicles.map((row): [string, string, BenchmarkPerformance | null | undefined] => [
      row.symbol + (row.theoretical ? ' · teórico' : ' · lo puedes comprar'),
      row.status === 'ok' ? row.label : 'Sin precios guardados: pulsa «Actualizar precios del índice».',
      row.performance,
    ]),
  ];
  return (
    <div className="mt-5 overflow-x-auto">
      <h3 className="font-semibold">El índice frente a los fondos que puedes comprar desde Europa</h3>
      <table className="mt-2 w-full text-left text-xs sm:text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="pb-2">Fondo</th>
            <th className="pb-2">Valor al final</th>
            <th className="pb-2">Costes</th>
            <th className="pb-2">TWR</th>
            <th className="pb-2">XIRR</th>
            <th className="pb-2">Mayor caída</th>
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
      <h3 className="font-semibold">¿Qué pasaría en una crisis?</h3>
      <p className="text-xs text-muted-foreground">
        Efecto inmediato sobre el valor actual. No son previsiones. {note}
      </p>
      <table className="mt-2 w-full text-left text-xs sm:text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="pb-2">Escenario</th>
            <th className="pb-2">Caída</th>
            <th className="pb-2">En euros</th>
            <th className="pb-2">¿Más de lo que aceptas?</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b last:border-0">
              <td className="py-2">{row.label}</td>
              <td className="py-2 tabular-nums">{pct(row.change)}</td>
              <td className="py-2 tabular-nums">{eur(row.change_eur)}</td>
              <td className="py-2">{row.exceeds_tolerance ? 'Sí: revisa tu plan' : 'No'}</td>
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
      <h3 className="font-semibold">Elegir acciones, mezclar o comprar el índice</h3>
      <p className="text-xs text-muted-foreground">
        Qué habría pasado con tus mismas compras si una parte hubiera ido al S&amp;P 500 (SPY) en
        vez de a tus acciones. Sirve para comparar, no es una recomendación.
      </p>
      <table className="mt-2 w-full text-left text-xs sm:text-sm">
        <thead className="border-b text-xs text-muted-foreground">
          <tr>
            <th className="pb-2">Opción</th>
            <th className="pb-2">Valor al final</th>
            <th className="pb-2">TWR</th>
            <th className="pb-2">XIRR</th>
            <th className="pb-2">Mayor caída</th>
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
      <h2 className="text-xl font-semibold">Mi cartera frente al S&amp;P 500 con el mismo dinero</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Cada compra de{' '}
        <Link className="text-primary underline" to="/cartera/mi-cartera">
          Mi cartera
        </Link>{' '}
        se compara con haber comprado el S&amp;P 500 (fondo SPY) el mismo día y por el mismo
        importe. En los dos casos se reinvierten los dividendos.
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
                '¿Cuánto más (o menos) tienes?',
                eur(data.comparison.wealth_difference_eur),
                'Mi cartera menos el S&P 500',
              ],
              ['Diferencia de rentabilidad (TWR)', pct(data.comparison.twr_difference), 'Sin importar cuándo aportaste'],
              ['Diferencia de tu rentabilidad anual (XIRR)', pct(data.comparison.xirr_difference), 'Contando cuándo aportaste'],
              [
                'Diferencia en la mayor caída',
                pct(data.comparison.max_drawdown_difference),
                'Si es positiva, tu cartera cayó menos',
              ],
            ]}
          />
          <h3 className="mt-5 font-semibold">Mi cartera</h3>
          <Cards items={performanceCards(data.portfolio)} />
          <h3 className="mt-5 font-semibold">El S&amp;P 500 con el mismo dinero</h3>
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
              'Parte de tu dinero que depende del dólar (si el dólar baja frente al euro, pierdes algo aunque la acción no se mueva): ' +
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
        eyebrow="Cartera"
        title="Mi perfil"
        description={
          <>
            Cuánto dinero tienes, cuánto aportas, cuánta caída aguantarías y qué habría pasado si
            lo hubieras invertido en el S&amp;P 500. Es la referencia con la que comparar a GABI.
          </>
        }
        guide={
          <p>
            Verás dos rentabilidades. La <strong>TWR</strong> mide cuánto rindió la inversión, sin
            importar cuándo metiste dinero: sirve para juzgar la estrategia. La{' '}
            <strong>XIRR</strong> mide lo que ganaste tú, contando cuándo aportaste: si metiste
            mucho justo antes de una caída, tu XIRR será peor aunque la estrategia sea la misma. Los
            datos son los guardados en tu equipo; solo «Actualizar precios del índice» descarga
            algo.
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
              Guarda tu perfil para ver qué habría pasado en el S&amp;P 500. Los valores que ves son
              un ejemplo: cámbialos por los tuyos.
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
