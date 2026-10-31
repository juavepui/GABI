import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { Holding, HoldingCreate, HoldingsSummary } from '@/shared/api/generated/types.gen';
import {
  createHolding,
  deleteHolding,
  getHoldings,
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
import { formatMoney, formatNumber, formatPercent } from '@/shared/lib/format';

const KEY = ['portfolio', 'holdings'];
const STATUS: Record<string, string> = {
  ok: '',
  missing_price: 'Sin precio en caché',
  missing_fx: 'Sin tipo de cambio en caché',
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
  return {
    symbol: String(form.get('symbol') ?? '').trim(),
    shares: Number(form.get('shares')),
    price: Number(form.get('price')),
    purchase_date: String(form.get('purchase_date') ?? ''),
    currency: String(form.get('currency') ?? 'USD') as HoldingCreate['currency'],
    commission: Number(form.get('commission') || 0),
    fx_rate: fx ? Number(fx) : null,
    note: String(form.get('note') ?? '').trim() || null,
  };
}

/** The same fields to register a purchase and to correct one. */
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
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(lotBody(new FormData(event.currentTarget)));
  }
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4">
      <label className="text-sm font-medium">
        Símbolo
        <Input className="mt-1" name="symbol" defaultValue={lot?.symbol} maxLength={20} required />
      </label>
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
      <label className="text-sm font-medium">
        Precio por acción
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
      <label className="text-sm font-medium">
        Fecha de compra
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
      <label className="text-sm font-medium">
        Euros por unidad (opcional)
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
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>
          <span className="font-medium">{lot.symbol}</span> ·{' '}
          {formatNumber(lot.shares, { digits: 4 })} acciones a {money(lot.price, currency)} el{' '}
          {lot.purchase_date}
          {commission > 0 && <> · comisión {money(commission, currency)}</>}
          {lot.note && <span className="ml-2 text-muted-foreground">{lot.note}</span>}
        </span>
        <span className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(!editing)}>
            {editing ? 'Cancelar' : 'Editar compra de ' + lot.symbol}
          </Button>
          <Button
            variant="outline"
            size="sm"
            pending={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Borrar compra de {lot.symbol}
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
    ['Coste', eur(totals.cost_eur), 'Con comisiones, en euros de cada compra'],
    ['Rentabilidad', pct(totals.return_eur), 'Precio, sin dividendos'],
    [
      'SPY en el mismo periodo',
      pct(totals.spy_return_eur),
      summary.benchmark_as_of ? 'Cierre del ' + summary.benchmark_as_of : 'Sin precio de SPY',
    ],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
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
      <h2 className="text-xl font-semibold">Posiciones</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-xs sm:text-sm">
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Empresa</th>
              <th className="pb-2 text-right">Acciones</th>
              <th className="pb-2 text-right">Precio medio</th>
              <th className="pb-2 text-right">Último cierre</th>
              <th className="pb-2 text-right">Valor</th>
              <th className="pb-2 text-right">Valor (€)</th>
              <th className="pb-2 text-right">Rentabilidad (€)</th>
              <th className="pb-2 text-right">SPY (€)</th>
              <th className="pb-2 text-right">Peso</th>
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
                    <span className="block text-xs text-amber-700 dark:text-amber-300">
                      {STATUS[row.status]}
                    </span>
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
      <h2 className="text-xl font-semibold">Frente a la cartera objetivo</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Peso actual de cada empresa frente a su peso en el Top-20 congelado de hoy. Una desviación
        no es una orden: el plan de aportación de{' '}
        <Link className="text-primary underline" to="/cartera">
          Cartera objetivo
        </Link>{' '}
        la reduce sin vender.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs sm:text-sm">
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Empresa</th>
              <th className="pb-2 text-right">Actual</th>
              <th className="pb-2 text-right">Objetivo</th>
              <th className="pb-2 text-right">Desviación (pp)</th>
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
                  <th className="pb-2 text-right">Diferencia (pp)</th>
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
    <Folded title="Importar CSV de un bróker">
      <p className="text-xs text-muted-foreground">
        Formato genérico con cabecera <code>symbol,shares,price,date,currency,commission</code>{' '}
        (fecha AAAA-MM-DD; divisa USD, EUR o GBP; comisión opcional). Con punto y coma como
        separador se admite la coma decimal. Si una fila no es válida no se importa ninguna.
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
        Importar compras
      </Button>
      {run.isError && <ErrorState error={run.error} retry={() => run.reset()} />}
      {run.data && (
        <p role="status" className="text-sm">
          Importadas {run.data.imported} compras.
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
        eyebrow="Cartera / Mi cartera"
        title="Mi cartera"
        description={
          <>
            Tus compras reales, guardadas en la base local. El valor usa el último cierre en caché;
            consultar no descarga precios y ninguna orden se envía a ningún sitio.
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
                  className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
                >
                  Sin valorar por falta de precio o de tipo de cambio en caché:{' '}
                  {data.missing.join(', ')}. No entran en los totales.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Todas las posiciones tienen precio y tipo de cambio en caché.
                </p>
              )}
              <HoldingsPrices summary={data} />
              <p className="mt-2 text-xs text-muted-foreground">{data.note}</p>
            </section>
          )}
          {data.positions.length > 0 && <Positions summary={data} />}
          {data.deviations.length > 0 && <Deviations summary={data} />}
          <section aria-label="Registrar una compra" className="rounded-xl border bg-card p-5">
            <h2 className="text-xl font-semibold">Registrar una compra</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Si tu bróker aplicó un tipo de cambio, anótalo en euros por unidad de la divisa; si
              no, se usa el de la caché en la fecha de compra.
            </p>
            <div className="mt-4">
              <LotForm
                key={formKey}
                label="Guardar compra"
                pending={add.isPending}
                onSubmit={(body) => add.mutate(body)}
              />
            </div>
            {add.isError && <ErrorState error={add.error} retry={() => add.reset()} />}
          </section>
          <ImportCsv changed={changed} />
          {data.lots.length > 0 && (
            <section aria-label="Compras registradas" className="rounded-xl border bg-card p-5">
              <h2 className="text-xl font-semibold">Compras registradas</h2>
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
