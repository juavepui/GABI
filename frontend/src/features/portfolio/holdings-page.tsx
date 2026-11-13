import { lazy, Suspense, useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type {
  Holding,
  HoldingCreate,
  HoldingsPerformance,
  HoldingsSummary,
} from '@/shared/api/generated/types.gen';
import {
  createHolding,
  deleteHolding,
  getHoldings,
  getHoldingsPerformance,
  getJobResult,
  importHoldings,
  updateHolding,
} from '@/shared/api/client';
import { useJob } from '@/shared/api/use-job';
import { ThesisMark } from './thesis-mark';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect } from '@/shared/ui/native-select';
import { Textarea } from '@/shared/ui/textarea';
import { Folded } from '@/shared/ui/folded';
import { PageHeader } from '@/shared/ui/page-header';
import { ProgressBar } from '@/shared/ui/progress-bar';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { dateLabel, formatMoney, formatNumber, formatPercent } from '@/shared/lib/format';
import { Term } from '@/shared/ui/term';

const PerformanceChart = lazy(() => import('./holdings-performance-chart'));

const KEY = ['portfolio', 'holdings'];
const KINDS: Record<string, { name: string; article: string }> = {
  buy: { name: 'compra', article: 'una compra' },
  sell: { name: 'venta', article: 'una venta' },
  dividend: { name: 'dividendo', article: 'un dividendo' },
};
const STATUS: Record<string, string> = {
  ok: '',
  missing_price: 'No hay precio guardado',
  missing_fx: 'No hay cambio de moneda guardado',
};
const eur = (value: number | null | undefined) =>
  formatMoney(value, { currency: 'EUR', digits: 2 });
const money = (value: number | null | undefined, currency: string) =>
  formatMoney(value, { currency, digits: 2 });
const pct = (value: number | null | undefined) => formatPercent(value, { signed: true });
const points = (value: number | null | undefined) =>
  formatNumber(value, { digits: 1, signed: true });

function lotBody(form: FormData): HoldingCreate {
  const fx = String(form.get('fx_rate') ?? '').trim();
  const kind = String(form.get('kind') ?? 'buy') as HoldingCreate['kind'];
  return {
    symbol: String(form.get('symbol') ?? '').trim(),
    kind,
    shares: kind === 'dividend' ? 0 : Number(form.get('shares')),
    withholding: kind === 'dividend' ? Number(form.get('withholding') || 0) : 0,
    price: Number(form.get('price')),
    purchase_date: String(form.get('purchase_date') ?? ''),
    basis_date: String(form.get('basis_date') ?? '').trim() || null,
    currency: String(form.get('currency') ?? 'USD') as HoldingCreate['currency'],
    commission: Number(form.get('commission') || 0),
    fx_rate: fx ? Number(fx) : null,
    note: String(form.get('note') ?? '').trim() || null,
  };
}

/** The same fields to register a purchase, a sale or a dividend and to correct one. */
function LotForm({
  lot,
  label,
  pending,
  onSubmit,
}: {
  lot?: Holding;
  label: string;
  pending: boolean;
  onSubmit: (body: HoldingCreate) => void;
}) {
  const [kind, setKind] = useState(lot?.kind ?? 'buy');
  const dividend = kind === 'dividend';
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(lotBody(new FormData(event.currentTarget)));
  }
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
      <label className="text-sm font-medium">
        Tipo de movimiento
        <NativeSelect
          name="kind"
          className="mt-1 w-full"
          value={kind}
          onChange={(event) => setKind(event.target.value as typeof kind)}
        >
          <option value="buy">Compra</option>
          <option value="sell">Venta</option>
          <option value="dividend">Dividendo cobrado</option>
        </NativeSelect>
      </label>
      <label className="text-sm font-medium">
        Símbolo
        <Input className="mt-1" name="symbol" defaultValue={lot?.symbol} maxLength={20} required />
      </label>
      {!dividend && (
        <label className="text-sm font-medium">
          Acciones
          <Input
            className="mt-1"
            name="shares"
            type="number"
            min={0}
            step="any"
            defaultValue={lot?.shares}
            required
          />
        </label>
      )}
      <label className="text-sm font-medium">
        {dividend ? 'Importe bruto cobrado' : 'Precio por acción'}
        <Input
          className="mt-1"
          name="price"
          type="number"
          min={0}
          step="any"
          defaultValue={lot?.price}
          required
        />
      </label>
      {dividend && (
        <label className="text-sm font-medium">
          Retención (impuesto descontado)
          <Input
            className="mt-1"
            name="withholding"
            type="number"
            min={0}
            step="any"
            defaultValue={lot?.withholding ?? 0}
          />
        </label>
      )}
      <label className="text-sm font-medium">
        Fecha
        <Input
          className="mt-1"
          name="purchase_date"
          type="date"
          defaultValue={lot?.purchase_date}
          required
        />
      </label>
      <label className="text-sm font-medium">
        Divisa
        <NativeSelect name="currency" className="mt-1 w-full" defaultValue={lot?.currency ?? 'USD'}>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
          <option value="GBP">GBP</option>
        </NativeSelect>
      </label>
      {!dividend && (
        <label className="text-sm font-medium sm:col-span-2">
          Ajuste del bróker: fecha de acciones y precio
          <Input
            className="mt-1"
            name="basis_date"
            type="date"
            defaultValue={lot?.basis_date ?? ''}
          />
          <span className="text-xs text-muted-foreground">
            Déjala vacía si anotas las acciones y el precio originales de esa compra o venta.
          </span>
        </label>
      )}
      {!dividend && (
        <label className="text-sm font-medium">
          Comisión (en esa divisa)
          <Input
            className="mt-1"
            name="commission"
            type="number"
            min={0}
            step="any"
            defaultValue={lot?.commission ?? 0}
          />
        </label>
      )}
      <label className="text-sm font-medium">
        Cambio aplicado: euros por cada dólar/libra (opcional)
        <Input
          className="mt-1"
          name="fx_rate"
          type="number"
          min={0}
          step="any"
          defaultValue={lot?.fx_rate ?? ''}
          placeholder="El de la caché"
        />
      </label>
      <label className="text-sm font-medium">
        Nota
        <Input className="mt-1" name="note" maxLength={200} defaultValue={lot?.note ?? ''} />
      </label>
      <div className="sm:col-span-4">
        <Button type="submit" pending={pending}>
          {label}
        </Button>
      </div>
    </form>
  );
}

function LotRow({ lot, changed }: { lot: Holding; changed: () => void }) {
  const [editing, setEditing] = useState(false);
  const update = useMutation({
    mutationFn: (body: HoldingCreate) => updateHolding(lot.id, body),
    onSuccess: () => {
      setEditing(false);
      changed();
    },
  });
  const remove = useMutation({ mutationFn: () => deleteHolding(lot.id), onSuccess: changed });
  const currency = lot.currency ?? 'USD';
  const commission = lot.commission ?? 0;
  const kind = KINDS[lot.kind ?? 'buy'];
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>
          <span className="font-medium">{lot.symbol}</span> · {kind.name}:{' '}
          {lot.kind === 'dividend' ? (
            <>
              {money(lot.price, currency)} brutos ({money(lot.withholding, currency)} de retención)
              el {lot.purchase_date}
            </>
          ) : (
            <>
              {formatNumber(lot.shares, { digits: 4 })} acciones a {money(lot.price, currency)} el{' '}
              {lot.purchase_date}
            </>
          )}
          {commission > 0 && <> · comisión {money(commission, currency)}</>}
          {lot.note && <span className="ml-2 text-muted-foreground">{lot.note}</span>}
        </span>
        <span className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(!editing)}>
            {editing ? 'Cancelar' : `Editar ${kind.name} de ${lot.symbol}`}
          </Button>
          <Button
            variant="outline"
            size="sm"
            pending={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Borrar {kind.name} de {lot.symbol}
          </Button>
        </span>
      </div>
      {editing && (
        <div className="mt-3 rounded-lg border p-3">
          <LotForm
            lot={lot}
            label="Guardar cambios"
            pending={update.isPending}
            onSubmit={(body) => update.mutate(body)}
          />
        </div>
      )}
      {update.isError && <ErrorState error={update.error} retry={() => update.reset()} />}
      {remove.isError && <ErrorState error={remove.error} retry={() => remove.reset()} />}
    </li>
  );
}

type PricesResult = { symbols: string[]; updated: number; failed: Record<string, string> };

/** The explicit download: a GET never fetches prices. */
function HoldingsPrices({ summary }: { summary: HoldingsSummary }) {
  const queryClient = useQueryClient();
  const { start, job } = useJob('holdings-prices');
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  const result = useQuery({
    queryKey: ['job', job.data?.id, 'result'],
    queryFn: ({ signal }) => getJobResult(job.data!.id, signal) as Promise<PricesResult>,
    enabled: job.data?.status === 'succeeded',
  });
  const done = result.data != null;
  useEffect(() => {
    if (done) void queryClient.invalidateQueries({ queryKey: KEY });
  }, [done, queryClient]);
  const failed = Object.entries(result.data?.failed ?? {});
  return (
    <div className="mt-3 space-y-2">
      <Button
        variant="outline"
        pending={running}
        onClick={() => start.mutate({ kind: 'holdings_prices' })}
      >
        Actualizar precios de mi cartera
      </Button>
      <p className="text-xs text-muted-foreground">
        Descarga de Yahoo Finance: {summary.price_symbols.join(', ')}. El worker la ejecuta aunque
        cierres el navegador.
      </p>
      {start.isError && <ErrorState error={start.error} retry={() => start.reset()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <ProgressBar value={job.data.progress} phase={job.data.phase} status={job.data.status} />
      )}
      {result.data && (
        <p role="status" className="text-sm">
          Actualizados {result.data.updated} símbolos; fallos: {failed.length}
          {failed.length > 0 && ' (' + failed.map(([name]) => name).join(', ') + ')'}.
        </p>
      )}
    </div>
  );
}

function Totals({ summary }: { summary: HoldingsSummary }) {
  const totals = summary.totals;
  if (!totals) return null;
  const cards: [string, string, string][] = [
    ['Valor actual', eur(totals.value_eur), `${totals.valued} de ${totals.positions} empresas`],
    ['Lo que pagaste', eur(totals.cost_eur), 'Con comisiones, en euros del día de cada compra'],
    [
      'Cuánto has ganado o perdido',
      pct(totals.return_eur),
      'Lo que aún tienes, solo por el precio',
    ],
    [
      'Ganado al vender',
      eur(totals.realized_eur),
      'Diferencia entre lo cobrado y lo que costaron esas acciones (a coste medio)',
    ],
    ['Dividendos cobrados', eur(totals.dividends_eur), 'Netos de la retención'],
    [
      'El S&P 500 (SPY) en el mismo tiempo',
      pct(totals.spy_return_eur),
      summary.benchmark_as_of
        ? 'Al cierre del ' + summary.benchmark_as_of
        : 'No hay precio del SPY',
    ],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      {cards.map(([label, value, hint]) => (
        <div key={label} className="rounded-xl border bg-card p-4">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </div>
      ))}
    </div>
  );
}

function Positions({ summary }: { summary: HoldingsSummary }) {
  return (
    <section aria-label="Posiciones" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Lo que tienes</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-xs sm:text-sm">
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Empresa</th>
              <th className="pb-2 text-right">Acciones</th>
              <th className="pb-2 text-right">Precio medio de compra</th>
              <th className="pb-2 text-right">Precio de hoy</th>
              <th className="pb-2 text-right">Valor</th>
              <th className="pb-2 text-right">Valor (€)</th>
              <th className="pb-2 text-right">Ganancia o pérdida (€)</th>
              <th className="pb-2 text-right">SPY (€)</th>
              <th className="pb-2 text-right">% de tu cartera</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {summary.positions.map((row) => (
              <tr key={row.symbol} className="border-b last:border-0">
                <td className="py-2">
                  <Link
                    className="font-medium text-primary"
                    to={'/empresas/' + encodeURIComponent(row.symbol)}
                  >
                    {row.symbol}
                  </Link>
                  <span className="block text-xs text-muted-foreground">
                    {row.sector ?? 'Sin sector'}
                    {row.in_target ? ' · en la cartera objetivo' : ''}
                  </span>
                  <ThesisMark symbol={row.symbol} />
                  {row.status !== 'ok' && (
                    <span className="block text-xs text-warning-ink">{STATUS[row.status]}</span>
                  )}
                </td>
                <td className="text-right">{formatNumber(row.shares, { digits: 4 })}</td>
                <td className="text-right">{money(row.average_price, row.currency)}</td>
                <td className="text-right">
                  {money(row.price, row.currency)}
                  <span className="block text-xs text-muted-foreground">
                    {row.price_date ?? '—'}
                  </span>
                </td>
                <td className="text-right">
                  {money(row.value, row.currency)}
                  <span className="block text-xs text-muted-foreground">
                    {pct(row.price_return)} en {row.currency}
                  </span>
                </td>
                <td className="text-right">{eur(row.value_eur)}</td>
                <td className="text-right">{pct(row.return_eur)}</td>
                <td className="text-right">{pct(row.spy_return_eur)}</td>
                <td className="text-right">
                  {row.weight_pct == null
                    ? '—'
                    : formatNumber(row.weight_pct, { digits: 1 }) + ' %'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Deviations({ summary }: { summary: HoldingsSummary }) {
  return (
    <section aria-label="Frente a la cartera objetivo" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Frente a la cartera que propone GABI</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Qué parte de tu cartera tiene cada empresa frente a la que tendría en la cartera propuesta
        hoy. Una diferencia no es una orden de vender: en{' '}
        <Link className="text-primary underline" to="/cartera">
          Cartera objetivo
        </Link>{' '}
        te dice dónde poner el dinero nuevo para acercarte sin vender.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs sm:text-sm">
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Empresa</th>
              <th className="pb-2 text-right">Tú</th>
              <th className="pb-2 text-right">Propuesta</th>
              <th className="pb-2 text-right">Diferencia (puntos %)</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {summary.deviations.map((row) => (
              <tr key={row.symbol} className="border-b last:border-0">
                <td className="py-2">{row.symbol}</td>
                <td className="text-right">
                  {row.weight_pct == null
                    ? '—'
                    : formatNumber(row.weight_pct, { digits: 1 }) + ' %'}
                </td>
                <td className="text-right">{formatNumber(row.target_pct, { digits: 1 })} %</td>
                <td className="text-right">{points(row.deviation_pp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {summary.sectors.length > 0 && (
        <div className="mt-4">
          <Folded title="Reparto por sector" className="rounded-lg border p-3 text-sm">
            <table className="w-full text-left text-xs sm:text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="pb-2">Sector</th>
                  <th className="pb-2 text-right">Mi cartera</th>
                  <th className="pb-2 text-right">S&amp;P 500</th>
                  <th className="pb-2 text-right">Diferencia (puntos %)</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {summary.sectors.map((row) => (
                  <tr key={row.sector} className="border-b last:border-0">
                    <td className="py-2">{row.sector}</td>
                    <td className="text-right">
                      {formatNumber(row.weight_percent, { digits: 1 })} %
                    </td>
                    <td className="text-right">
                      {formatNumber(row.index_weight_percent, { digits: 1 })} %
                    </td>
                    <td className="text-right">{points(row.difference_points)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Folded>
        </div>
      )}
    </section>
  );
}

const BLOCKED: Record<string, string> = {
  missing_fx: 'falta el cambio de moneda de ese día',
  after_last_session: 'es posterior al último precio guardado',
};

function RiskCards({ risk }: { risk: NonNullable<HoldingsPerformance['portfolio']> }) {
  const fall =
    risk.max_drawdown < 0
      ? `Del ${dateLabel(risk.peak_date)} al ${dateLabel(risk.trough_date)}; ${
          risk.recovered_date
            ? 'recuperada el ' + dateLabel(risk.recovered_date)
            : 'aún sin recuperar'
        }`
      : 'No ha caído desde ningún máximo';
  const cards: [React.ReactNode, string, string][] = [
    [
      <Term key="twr" k="twr">
        Rentabilidad de tus elecciones
      </Term>,
      pct(risk.twr),
      risk.twr_annualised == null
        ? 'Desde el principio; sin anualizar (menos de un año)'
        : `${pct(risk.twr_annualised)} al año`,
    ],
    [
      <Term key="mw" k="money_weighted">
        Rentabilidad de tu dinero
      </Term>,
      risk.money_weighted == null ? '—' : pct(risk.money_weighted) + ' al año',
      risk.money_weighted == null
        ? 'Hace falta al menos un año de historia'
        : 'Teniendo en cuenta cuándo metiste y sacaste dinero',
    ],
    [
      <Term key="dd" k="max_drawdown">
        La mayor caída desde un máximo
      </Term>,
      pct(risk.max_drawdown),
      fall,
    ],
    [
      <Term key="vol" k="volatility">
        Cuánto se mueve (volatilidad)
      </Term>,
      risk.volatility == null ? '—' : formatPercent(risk.volatility) + ' al año',
      'Cuanto más alta, más sube y baja de un día a otro',
    ],
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map(([label, value, hint], index) => (
        <div key={index} className="rounded-lg border p-3">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>
          <dd className="text-xs text-muted-foreground">{hint}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Evolución (#294): the daily series, returns, risk, attribution and the S&P 500 with the same euros. */
function Evolution() {
  const query = useQuery({
    queryKey: [...KEY, 'performance'],
    queryFn: ({ signal }) => getHoldingsPerformance(signal),
  });
  return (
    <section aria-label="Evolución de tu cartera" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Cómo ha ido tu cartera</h2>
      {query.isPending && <LoadingState />}
      {query.isError && <ErrorState error={query.error} retry={() => void query.refetch()} />}
      {query.data && <EvolutionContent data={query.data} />}
      {query.data?.warnings?.map((warning) => (
        <p key={warning.symbol} role="status" className="mt-2 text-sm text-warning-ink">
          {warning.message}
        </p>
      ))}
    </section>
  );
}

function EvolutionContent({ data }: { data: HoldingsPerformance }) {
  if (data.status === 'blocked')
    return (
      <p role="status" className="mt-2 text-sm">
        No se puede calcular la evolución porque falta un dato de estos movimientos:{' '}
        {(data.blocked ?? [])
          .map((row) => `${row.symbol} del ${row.date} (${BLOCKED[row.reason] ?? row.reason})`)
          .join('; ')}
        . Pulsa «Actualizar precios de mi cartera» o anota el cambio que aplicó tu bróker.
      </p>
    );
  if (data.status !== 'ok' || !data.portfolio)
    return (
      <p className="mt-2 text-sm">
        Todavía no hay ningún día con precio para todas tus empresas. Actualiza los precios.
      </p>
    );
  const risk = data.portfolio;
  const spy = data.benchmark?.status === 'ok' && data.benchmark.twr != null ? data.benchmark : null;
  const gaps = data.gaps ?? [];
  const gapSessions = data.gap_sessions ?? 0;
  const attribution = data.attribution?.status === 'ok' ? data.attribution : null;
  return (
    <div className="mt-3 space-y-4 text-sm">
      <p>
        Del {dateLabel(risk.start)} al {dateLabel(risk.end)} tu cartera ha rendido{' '}
        <strong>{pct(risk.twr)}</strong>
        {spy && (
          <>
            {' '}
            frente al <strong>{pct(spy.twr)}</strong> del S&amp;P 500 con el mismo dinero los mismos
            días ({risk.twr >= (spy.twr ?? 0) ? 'por encima' : 'por debajo'})
          </>
        )}
        . El pasado no garantiza el futuro, y con poco tiempo la diferencia puede ser suerte.
      </p>
      <RiskCards risk={risk} />
      <Suspense fallback={<LoadingState />}>
        <PerformanceChart portfolio={risk.series} benchmark={spy?.series ?? []} />
      </Suspense>
      {spy && (
        <Folded title="El S&P 500 con el mismo dinero" className="rounded-lg border p-3">
          <RiskCards risk={spy as NonNullable<HoldingsPerformance['portfolio']>} />
          <p className="mt-2 text-xs text-muted-foreground">
            SPY con los dividendos reinvertidos, en euros: compra cuando tú compras y vende cuando
            tú vendes o cobras un dividendo, por los mismos euros.
            {spy.shortfall_eur
              ? ` Faltó SPY para igualar ${eur(spy.shortfall_eur)} de retiradas.`
              : ''}
          </p>
        </Folded>
      )}
      {attribution && (
        <div>
          <h3 className="font-medium">
            <Term k="attribution">De dónde sale lo que has ganado</Term>
          </h3>
          <p className="text-xs text-muted-foreground">
            Sobre los {eur(attribution.bought_eur)} que has comprado has ganado{' '}
            {eur(attribution.gain_eur)} ({pct(attribution.return_on_bought)}): valor de hoy + ventas
            + dividendos netos − compras. Los puntos de cada fila suman ese total.
          </p>
          <div className="mt-2 grid gap-4 lg:grid-cols-2">
            <table className="w-full text-left text-xs" aria-label="Atribución por empresa">
              <thead className="border-b text-muted-foreground">
                <tr>
                  <th className="py-1.5">Empresa</th>
                  <th className="text-right">Ganancia (€)</th>
                  <th className="text-right">Puntos %</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {(attribution.positions ?? []).map((row) => (
                  <tr key={row.symbol} className="border-b last:border-0">
                    <td className="py-1.5">
                      {row.symbol}
                      {!row.open && <span className="text-muted-foreground"> · vendida</span>}
                    </td>
                    <td className="text-right">{eur(row.gain_eur)}</td>
                    <td className="text-right">{points(row.contribution_pp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="w-full text-left text-xs" aria-label="Atribución por sector">
              <thead className="border-b text-muted-foreground">
                <tr>
                  <th className="py-1.5">Sector</th>
                  <th className="text-right">Ganancia (€)</th>
                  <th className="text-right">Puntos %</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {(attribution.sectors ?? []).map((row) => (
                  <tr key={row.sector} className="border-b last:border-0">
                    <td className="py-1.5">{row.sector}</td>
                    <td className="text-right">{eur(row.gain_eur)}</td>
                    <td className="text-right">{points(row.contribution_pp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {gapSessions > 0 && (
        <p className="text-xs text-muted-foreground" role="status">
          {gapSessions} {gapSessions === 1 ? 'día se ha saltado' : 'días se han saltado'} porque
          faltaba el precio o el cambio de alguna empresa (no se rellenan): por ejemplo, el{' '}
          {gaps[0].date} ({gaps[0].symbols.join(', ')}).
        </p>
      )}
      <p className="text-xs text-muted-foreground">{data.note}</p>
    </div>
  );
}

function ImportCsv({ changed }: { changed: () => void }) {
  const [text, setText] = useState('');
  const run = useMutation({
    mutationFn: () => importHoldings(text),
    onSuccess: () => {
      setText('');
      changed();
    },
  });
  return (
    <Folded title="Importar tus movimientos desde un fichero de tu bróker (CSV)">
      <p className="text-xs text-muted-foreground">
        Formato genérico con cabecera <code>symbol,shares,price,date,currency,commission</code>{' '}
        (fecha AAAA-MM-DD; divisa USD, EUR o GBP; comisión opcional). Para ventas y dividendos,
        añade las columnas <code>type</code> (compra, venta o dividendo) y <code>withholding</code>{' '}
        (retención); en un dividendo, <code>price</code> es el importe bruto cobrado. Con punto y
        coma como separador se admite la coma decimal. Si una fila no es válida no se importa
        ninguna. Si el bróker reajustó las acciones y el precio por un desdoblamiento, añade
        <code> basis_date</code> con la fecha de ese ajuste; si son los datos originales, déjala
        vacía.
      </p>
      <label className="block text-sm font-medium" htmlFor="holdings-csv">
        Contenido del CSV
      </label>
      <Textarea
        id="holdings-csv"
        rows={5}
        value={text}
        maxLength={100000}
        onChange={(event) => setText(event.target.value)}
        placeholder={
          'symbol,shares,price,date,currency,commission\nAAPL,10,150.25,2025-03-14,USD,1'
        }
        className="w-full"
      />
      <Button disabled={!text.trim()} pending={run.isPending} onClick={() => run.mutate()}>
        Importar movimientos
      </Button>
      {run.isError && <ErrorState error={run.error} retry={() => run.reset()} />}
      {run.data && (
        <p role="status" className="text-sm">
          Importados {run.data.imported} movimientos.
        </p>
      )}
    </Folded>
  );
}

export function HoldingsPage() {
  const queryClient = useQueryClient();
  const summary = useQuery({ queryKey: KEY, queryFn: ({ signal }) => getHoldings(signal) });
  const changed = () => void queryClient.invalidateQueries({ queryKey: ['portfolio'] });
  const [formKey, setFormKey] = useState(0);
  const add = useMutation({
    mutationFn: createHolding,
    onSuccess: () => {
      setFormKey((key) => key + 1);
      changed();
    },
  });
  const data = summary.data;
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Cartera"
        title="Mi cartera"
        description={
          <>
            Apunta aquí lo que compras de verdad para ver cuánto vale, cuánto ganas o pierdes y cómo
            va frente al S&amp;P 500. Se guarda solo en tu equipo y GABI nunca compra ni vende por
            ti.
          </>
        }
      />
      {summary.isPending && <LoadingState />}
      {summary.isError && <ErrorState error={summary.error} retry={() => void summary.refetch()} />}
      {data && (
        <>
          <Totals summary={data} />
          {data.lots.length > 0 && (
            <section aria-label="Precios de mi cartera" className="rounded-xl border bg-card p-5">
              {data.missing.length > 0 ? (
                <p
                  role="status"
                  className="rounded-lg border border-warning-border bg-warning-soft p-3 text-sm text-warning-ink"
                >
                  No se han podido valorar porque falta su precio o el cambio de moneda:{' '}
                  {data.missing.join(', ')}. No cuentan en los totales; pulsa «Actualizar precios de
                  mi cartera».
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Todas tus empresas tienen precio y cambio de moneda guardados.
                </p>
              )}
              <HoldingsPrices summary={data} />
              {data.warnings?.map((warning) => (
                <p key={warning.symbol} role="status" className="mt-2 text-sm text-warning-ink">
                  {warning.message}
                </p>
              ))}
              <p className="mt-2 text-xs text-muted-foreground">{data.note}</p>
            </section>
          )}
          {data.positions.length > 0 && <Positions summary={data} />}
          {data.lots.length > 0 && <Evolution />}
          {data.deviations.length > 0 && <Deviations summary={data} />}
          <section aria-label="Registrar un movimiento" className="rounded-xl border bg-card p-5">
            <h2 className="text-xl font-semibold">Apuntar una compra, una venta o un dividendo</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Si tu bróker aplicó un tipo de cambio, anótalo en euros por unidad de la divisa; si
              no, se usa el de la caché en esa fecha. No se puede vender más de lo que tenías ese
              día ni apuntar un dividendo de una empresa que no tenías.
            </p>
            <div className="mt-4">
              <LotForm
                key={formKey}
                label="Guardar movimiento"
                pending={add.isPending}
                onSubmit={(body) => add.mutate(body)}
              />
            </div>
            {add.isError && <ErrorState error={add.error} retry={() => add.reset()} />}
          </section>
          <ImportCsv changed={changed} />
          {data.lots.length > 0 && (
            <section aria-label="Movimientos registrados" className="rounded-xl border bg-card p-5">
              <h2 className="text-xl font-semibold">Movimientos apuntados</h2>
              <ul className="mt-2 divide-y">
                {data.lots.map((lot) => (
                  <LotRow key={lot.id + ':' + lot.updated_at} lot={lot} changed={changed} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
