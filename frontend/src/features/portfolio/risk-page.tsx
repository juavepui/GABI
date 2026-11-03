import { useState, type FormEvent, type ReactNode } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type {
  GroupWeight,
  PolicyAlternative,
  PortfolioPolicyInput,
  PortfolioPolicyRevision,
  RiskPanel,
} from '@/shared/api/generated/types.gen';
import {
  ApiError,
  getPolicyProposal,
  getPortfolioPolicy,
  getRiskPanel,
  savePortfolioPolicy,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { PageHeader } from '@/shared/ui/page-header';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatMoney, formatNumber, formatPercent } from '@/shared/lib/format';

const KEY = ['portfolio', 'risk'];
const eur = (value: number | null | undefined) =>
  formatMoney(value, { currency: 'EUR', digits: 2 });
const pct = (value: number | null | undefined) => formatPercent(value, { digits: 1 });
const BLOCKS: Record<string, string> = {
  value: 'Valor',
  quality: 'Calidad',
  momentum: 'Momentum',
  risk: 'Riesgo',
};
const EXCLUDED: Record<string, string> = {
  no_price: 'sin precio en caché',
  illiquid: 'volumen diario por debajo del mínimo',
};

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="text-sm font-medium">
      {label}
      {children}
      {hint && <span className="mt-1 block text-xs font-normal text-muted-foreground">{hint}</span>}
    </label>
  );
}

function Weights({ title, rows }: { title: string; rows: GroupWeight[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-1 space-y-0.5 text-sm">
        {rows.map((row) => (
          <li key={row.name} className={row.exceeds ? 'font-medium text-destructive' : ''}>
            {row.name}: {pct(row.weight)}
            {row.exceeds && ' · supera el límite'}
          </li>
        ))}
      </ul>
    </div>
  );
}

type SavePolicy = UseMutationResult<PortfolioPolicyRevision, Error, PortfolioPolicyInput>;

/** Percentages are typed in % and sent as fractions. The mutation lives in the page, so the
 *  confirmation survives the remount a new revision causes. */
function PolicyForm({
  policy,
  revision,
  save,
}: {
  policy: PortfolioPolicyInput;
  revision: number | null;
  save: SavePolicy;
}) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const share = (name: string) => Number(form.get(name) || 0) / 100;
    save.mutate({
      max_issuer_weight: share('max_issuer_weight'),
      max_sector_weight: share('max_sector_weight'),
      cash_weight: share('cash_weight'),
      min_daily_dollar_volume: Number(form.get('min_daily_dollar_volume') || 0) * 1e6,
      participation: share('participation'),
      max_cost_share: share('max_cost_share'),
    });
  }
  const percent = (value: number | undefined) => String(Math.round((value ?? 0) * 10000) / 100);
  return (
    <form
      onSubmit={submit}
      aria-label="Política de cartera"
      className="rounded-xl border bg-card p-5"
    >
      <h2 className="text-xl font-semibold">Tus límites</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {revision
          ? `Versión ${revision} de tus límites.`
          : 'Son valores de ejemplo: guárdalos para fijarlos.'}{' '}
        Nunca se invierte dinero prestado: lo invertido más lo que queda sin invertir suma siempre
        el 100 %. Estos límites no cambian aunque cambie la versión del modelo.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Field
          label="Máximo en una sola empresa (%)"
          hint="Si una empresa tiene varios tipos de acciones (p. ej. GOOG y GOOGL), cuentan juntas."
        >
          <Input
            className="mt-1.5"
            name="max_issuer_weight"
            type="number"
            min={1}
            max={100}
            step="0.1"
            defaultValue={percent(policy.max_issuer_weight)}
            required
          />
        </Field>
        <Field label="Máximo en un mismo sector (%)">
          <Input
            className="mt-1.5"
            name="max_sector_weight"
            type="number"
            min={1}
            max={100}
            step="0.1"
            defaultValue={percent(policy.max_sector_weight)}
            required
          />
        </Field>
        <Field label="Dinero que dejas sin invertir (%)">
          <Input
            className="mt-1.5"
            name="cash_weight"
            type="number"
            min={0}
            max={99}
            step="0.1"
            defaultValue={percent(policy.cash_weight)}
          />
        </Field>
        <Field
          label="Negociación diaria mínima (millones USD)"
          hint="Deja fuera acciones que se compran y venden poco, porque pueden ser difíciles de vender."
        >
          <Input
            className="mt-1.5"
            name="min_daily_dollar_volume"
            type="number"
            min={0}
            step="0.1"
            defaultValue={(policy.min_daily_dollar_volume ?? 0) / 1e6}
          />
        </Field>
        <Field
          label="Qué parte de lo negociado al día podrías vender tú (%)"
          hint="Sirve para estimar cuántos días tardarías en vender sin mover el precio."
        >
          <Input
            className="mt-1.5"
            name="participation"
            type="number"
            min={0.1}
            max={100}
            step="0.1"
            defaultValue={percent(policy.participation)}
          />
        </Field>
        <Field
          label="Comisión máxima por compra (%)"
          hint="Si una compra pequeña sale cara en comisiones, se espera a juntarla con otras."
        >
          <Input
            className="mt-1.5"
            name="max_cost_share"
            type="number"
            min={0.01}
            max={20}
            step="0.01"
            defaultValue={percent(policy.max_cost_share)}
          />
        </Field>
      </div>
      <Button className="mt-4" type="submit" pending={save.isPending}>
        Guardar límites
      </Button>
      {save.isSuccess && (
        <p role="status" className="mt-2 text-sm">
          Guardada como revisión {save.data.revision}.
        </p>
      )}
      {save.isError && <ErrorState error={save.error} retry={() => save.reset()} />}
    </form>
  );
}

function Panel({ data }: { data: RiskPanel }) {
  const { exposure, stress } = data;
  if (data.positions === 0) {
    return (
      <section aria-label="Exposición de Mi cartera" className="rounded-xl border bg-card p-5">
        <h2 className="text-xl font-semibold">De qué depende Mi cartera</h2>
        <p className="mt-2 text-sm">
          Sin posiciones valoradas.{' '}
          <Link className="text-primary underline" to="/cartera/mi-cartera">
            Registra tus compras en Mi cartera
          </Link>{' '}
          y actualiza sus precios.
        </p>
      </section>
    );
  }
  return (
    <section aria-label="Exposición de Mi cartera" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">De qué depende Mi cartera</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {data.positions} posiciones valoradas por {eur(exposure.total_eur)}.
        {data.unvalued.length > 0 && ' Sin valorar: ' + data.unvalued.join(', ') + '.'}
      </p>
      {exposure.breaches.length > 0 && (
        <ul role="alert" className="mt-3 list-disc pl-5 text-sm text-destructive">
          {exposure.breaches.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      )}
      <div className="mt-4 overflow-x-auto">
        <h3 className="text-sm font-semibold">Por empresa</h3>
        <table className="mt-1 w-full text-left text-xs sm:text-sm">
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Empresa</th>
              <th className="pb-2">Acciones</th>
              <th className="pb-2">% de tu cartera</th>
            </tr>
          </thead>
          <tbody>
            {exposure.issuers.map((row) => (
              <tr key={row.issuer} className="border-b last:border-0">
                <td className="py-1.5">{row.issuer}</td>
                <td className="py-1.5">{row.symbols.join(', ')}</td>
                <td className={'py-1.5 tabular-nums ' + (row.exceeds ? 'text-destructive' : '')}>
                  {pct(row.weight)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Weights title="Sector" rows={exposure.sectors} />
        <Weights title="Moneda en la que cotiza" rows={exposure.listing_currency} />
        <Weights title="Moneda de sus negocios" rows={exposure.economic_currency} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{data.economic_currency_note}</p>
      <h3 className="mt-4 text-sm font-semibold">
        Puntuación media de tu cartera en cada apartado (0–100)
      </h3>
      <p className="text-sm">
        {Object.entries(exposure.factors)
          .map(
            ([block, tilt]) =>
              `${BLOCKS[block] ?? block} ${formatNumber(tilt.score, { digits: 0 })} (${pct(tilt.coverage)} con dato)`,
          )
          .join(' · ')}
      </p>
      <h3 className="mt-4 text-sm font-semibold">¿Cuánto tardarías en vender? (liquidez)</h3>
      <ul className="mt-1 text-sm">
        {exposure.liquidity.map((row) => (
          <li key={row.symbol}>
            {row.symbol}:{' '}
            {row.days_to_trade == null
              ? 'no se sabe cuánto se negocia'
              : formatNumber(row.days_to_trade, { digits: 2 }) + ' días de bolsa para venderla'}
            {row.illiquid && row.days_to_trade != null && ' · más de un día'}
          </li>
        ))}
      </ul>
      <h3 className="mt-4 text-sm font-semibold">¿Qué pasaría en una crisis?</h3>
      <table className="mt-1 w-full text-left text-xs sm:text-sm">
        <tbody>
          {stress.scenarios.map((row) => (
            <tr key={row.id} className="border-b last:border-0">
              <td className="py-1.5">{row.label}</td>
              <td className="py-1.5 tabular-nums">{pct(row.change)}</td>
              <td className="py-1.5 tabular-nums">{eur(row.change_eur)}</td>
              <td className="py-1.5">
                {row.exceeds_tolerance ? 'Más de la caída que aceptas' : 'Dentro de lo que aceptas'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
        {stress.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  );
}

function Alternative({ data }: { data: PolicyAlternative }) {
  return (
    <div className="rounded-lg border p-4">
      <h3 className="font-semibold">{data.label}</h3>
      <p className="mt-1 text-sm">
        {data.weights.length} empresas · sin invertir {pct(data.cash)}
      </p>
      {data.breaches.length > 0 ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-destructive">
          {data.breaches.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm">Cumple todos tus límites.</p>
      )}
      <h4 className="mt-3 text-sm font-semibold">Qué comprar con tu aportación</h4>
      {data.orders.length ? (
        <table className="mt-1 w-full text-left text-xs">
          <thead className="border-b text-muted-foreground">
            <tr>
              <th className="pb-1">Empresa</th>
              <th className="pb-1">Acciones</th>
              <th className="pb-1">Importe</th>
              <th className="pb-1">Comisión</th>
              <th className="pb-1">Divisa</th>
            </tr>
          </thead>
          <tbody>
            {data.orders.map((row) => (
              <tr key={row.symbol} className="border-b last:border-0">
                <td className="py-1">{row.symbol}</td>
                <td className="py-1 tabular-nums">{formatNumber(row.shares, { digits: 4 })}</td>
                <td className="py-1 tabular-nums">{eur(row.amount_eur)}</td>
                <td className="py-1 tabular-nums">{eur(row.commission_eur)}</td>
                <td className="py-1 tabular-nums">{eur(row.fx_cost_eur)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-1 text-sm">
          Con esta aportación ninguna compra llega al mínimo sin pasarse de la comisión máxima.
        </p>
      )}
      <p className="mt-2 text-sm">
        Costes {eur(data.costs_eur)} · efectivo sin invertir {eur(data.residual_cash_eur)}
      </p>
      {data.unfunded.length > 0 && (
        <p className="mt-1 text-xs text-muted-foreground">
          Quedan para próximas aportaciones: {data.unfunded.join(', ')}.
        </p>
      )}
    </div>
  );
}

function Proposal() {
  const [request, setRequest] = useState({ contribution: 700, positions: 20 });
  const proposal = useQuery({
    queryKey: [...KEY, 'proposal', request],
    queryFn: ({ signal }) => getPolicyProposal(request.contribution, request.positions, signal),
    retry: false,
  });
  const missingRate =
    proposal.error instanceof ApiError && proposal.error.code === 'benchmark_prices_missing';
  return (
    <section aria-label="Equiponderada frente a política" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Reparto a partes iguales frente a tus límites</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Las mismas empresas mejor puntuadas, primero con el mismo dinero en cada una y después
        respetando tus límites, y qué comprar con tu aportación sin vender nada. Son propuestas:
        GABI nunca compra por ti. El número de empresas lo eliges tú.
      </p>
      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          setRequest({
            contribution: Number(form.get('contribution')),
            positions: Number(form.get('positions')),
          });
        }}
      >
        <Field label="Dinero que vas a aportar (€)">
          <Input
            className="mt-1.5"
            name="contribution"
            type="number"
            min={0}
            step="0.01"
            defaultValue={request.contribution}
          />
        </Field>
        <Field label="Número de empresas">
          <Input
            className="mt-1.5"
            name="positions"
            type="number"
            min={5}
            max={30}
            defaultValue={request.positions}
          />
        </Field>
        <Button type="submit" variant="outline" pending={proposal.isFetching}>
          Proponer
        </Button>
      </form>
      {proposal.isPending && <LoadingState />}
      {missingRate && (
        <p className="mt-3 text-sm">
          {proposal.error?.message}{' '}
          <Link className="text-primary underline" to="/cartera/perfil">
            Ir a Mi perfil
          </Link>
        </p>
      )}
      {proposal.isError && !missingRate && (
        <ErrorState error={proposal.error} retry={() => void proposal.refetch()} />
      )}
      {proposal.data && (
        <>
          {proposal.data.excluded.length > 0 && (
            <p className="mt-3 text-sm">
              Fuera por elegibilidad:{' '}
              {proposal.data.excluded
                .map((row) => `${row.symbol} (${EXCLUDED[row.reason] ?? row.reason})`)
                .join(', ')}
              .
            </p>
          )}
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {proposal.data.alternatives.map((row) => (
              <Alternative key={row.label} data={row} />
            ))}
          </div>
          {proposal.data.outside_target.length > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              Fuera del Top actual: {proposal.data.outside_target.join(', ')}. No se proponen
              ventas.
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function RiskPage() {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: savePortfolioPolicy,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
  const policy = useQuery({
    queryKey: [...KEY, 'policy'],
    queryFn: ({ signal }) => getPortfolioPolicy(signal),
  });
  const panel = useQuery({
    queryKey: [...KEY, 'panel'],
    queryFn: ({ signal }) => getRiskPanel(signal),
  });
  const current = policy.data?.current;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cartera"
        title="Riesgo y límites"
        description={
          <>
            Cuánto depende tu cartera de cada empresa, sector y moneda, y unos límites para no poner
            demasiados huevos en la misma cesta. GABI nunca compra ni vende por ti.
          </>
        }
        guide={
          <p>
            La cartera propuesta solo te avisa si se concentra mucho; aquí puedes fijar límites de
            verdad: cuánto como mucho en una empresa o un sector, cuánto dejar sin invertir y qué
            acciones descartar por ser difíciles de vender. Nunca se invierte dinero prestado. Todo
            se calcula con los datos guardados en tu equipo.
          </p>
        }
      />
      {policy.isPending && <LoadingState />}
      {policy.isError && <ErrorState error={policy.error} retry={() => void policy.refetch()} />}
      {policy.data && (
        <PolicyForm
          key={current?.revision ?? 0}
          policy={current ? current.profile : policy.data.default}
          revision={current?.revision ?? null}
          save={save}
        />
      )}
      {panel.isPending && <LoadingState />}
      {panel.isError && <ErrorState error={panel.error} retry={() => void panel.refetch()} />}
      {panel.data && <Panel data={panel.data} />}
      <Proposal />
    </div>
  );
}
