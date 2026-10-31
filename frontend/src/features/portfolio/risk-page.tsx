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
      <h2 className="text-xl font-semibold">Política de cartera</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {revision ? `Revisión ${revision}.` : 'Valores por defecto: guarda para fijarlos.'} Sin
        apalancamiento: los pesos y la caja suman siempre el 100 %. Independiente de las versiones
        del modelo.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Field
          label="Peso máximo por emisor (%)"
          hint="Las clases de un mismo emisor suman juntas."
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
        <Field label="Peso máximo por sector (%)">
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
        <Field label="Reserva de caja (%)">
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
        <Field label="Volumen diario mínimo (millones USD)" hint="Elegibilidad por liquidez.">
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
          label="Parte negociable del volumen (%)"
          hint="Para estimar los días que tardaría en venderse."
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
        <Field label="Coste máximo por orden (%)" hint="Una orden más cara se agrupa con otras.">
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
        Guardar política
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
        <h2 className="text-xl font-semibold">Exposición de Mi cartera</h2>
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
      <h2 className="text-xl font-semibold">Exposición de Mi cartera</h2>
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
        <h3 className="text-sm font-semibold">Por emisor</h3>
        <table className="mt-1 w-full text-left text-xs sm:text-sm">
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Emisor</th>
              <th className="pb-2">Valores</th>
              <th className="pb-2">Peso</th>
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
        <Weights title="Moneda de cotización" rows={exposure.listing_currency} />
        <Weights title="Exposición económica" rows={exposure.economic_currency} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{data.economic_currency_note}</p>
      <h3 className="mt-4 text-sm font-semibold">Factores (media ponderada, 0–100)</h3>
      <p className="text-sm">
        {Object.entries(exposure.factors)
          .map(
            ([block, tilt]) =>
              `${BLOCKS[block] ?? block} ${formatNumber(tilt.score, { digits: 0 })} (${pct(tilt.coverage)} con dato)`,
          )
          .join(' · ')}
      </p>
      <h3 className="mt-4 text-sm font-semibold">Liquidez</h3>
      <ul className="mt-1 text-sm">
        {exposure.liquidity.map((row) => (
          <li key={row.symbol}>
            {row.symbol}:{' '}
            {row.days_to_trade == null
              ? 'sin volumen en caché'
              : formatNumber(row.days_to_trade, { digits: 2 }) + ' sesiones para venderla'}
            {row.illiquid && row.days_to_trade != null && ' · más de una sesión'}
          </li>
        ))}
      </ul>
      <h3 className="mt-4 text-sm font-semibold">Estrés</h3>
      <table className="mt-1 w-full text-left text-xs sm:text-sm">
        <tbody>
          {stress.scenarios.map((row) => (
            <tr key={row.id} className="border-b last:border-0">
              <td className="py-1.5">{row.label}</td>
              <td className="py-1.5 tabular-nums">{pct(row.change)}</td>
              <td className="py-1.5 tabular-nums">{eur(row.change_eur)}</td>
              <td className="py-1.5">{row.exceeds_tolerance ? 'Supera tu tolerancia' : '—'}</td>
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
        {data.weights.length} posiciones · caja {pct(data.cash)}
      </p>
      {data.breaches.length > 0 ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-destructive">
          {data.breaches.map((text) => (
            <li key={text}>{text}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm">Dentro de los límites de la política.</p>
      )}
      <h4 className="mt-3 text-sm font-semibold">Órdenes para tu aportación</h4>
      {data.orders.length ? (
        <table className="mt-1 w-full text-left text-xs">
          <thead className="border-b text-muted-foreground">
            <tr>
              <th className="pb-1">Valor</th>
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
        <p className="mt-1 text-sm">Ninguna orden supera el mínimo y el coste máximo.</p>
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
      <h2 className="text-xl font-semibold">Equiponderada frente a la política</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        La misma selección Top-N con pesos iguales y con los límites de la política, y las compras
        que necesitaría tu aportación sin vender nada. Son propuestas: GABI no envía órdenes. El
        número de posiciones lo eliges tú; no se ajusta para mejorar resultados pasados.
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
        <Field label="Aportación (€)">
          <Input
            className="mt-1.5"
            name="contribution"
            type="number"
            min={0}
            step="0.01"
            defaultValue={request.contribution}
          />
        </Field>
        <Field label="Posiciones">
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
            Ir a Perfil y benchmark
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
        eyebrow="Cartera / Riesgo"
        title="Riesgo y política"
        description={
          <>
            Cuánto depende tu cartera de cada emisor, sector y moneda, y una política con límites
            para capital y aportaciones pequeños. No activa ninguna cartera ni envía órdenes.
          </>
        }
        guide={
          <p>
            Avisar de una concentración no la limita: la política fija pesos máximos por emisor y
            sector, sin apalancamiento, y descarta lo ilíquido. Dos clases de acciones del mismo
            emisor cuentan como un solo riesgo. Todo sale de la caché local.
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
