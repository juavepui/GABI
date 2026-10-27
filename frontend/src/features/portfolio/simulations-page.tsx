import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  SimulationPortfolio,
  SimulationResult,
  SimulationTradeCreate,
} from '@/shared/api/generated/types.gen';
import {
  ApiError,
  createJob,
  createSimulation,
  createSimulationTrade,
  getJob,
  getJobResult,
  getSimulationResult,
  getSimulations,
  getSimulationTrades,
  undoSimulationTrade,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { AdvancedOptions, HelpField } from '@/shared/ui/advanced-options';
import { useFormDefaults } from '@/shared/api/use-form-defaults';
import { useJob } from '@/shared/api/use-job';
import { Input } from '@/shared/ui/input';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Badge } from '@/shared/ui/badge';
import { SimulationPrices } from './sim-prices';
import { dateText, formatNumber } from '@/shared/lib/format';
import { PageHeader } from '@/shared/ui/page-header';
import { NativeSelect } from '@/shared/ui/native-select';

const SimulationChart = lazy(() => import('./simulation-chart'));
const number = (value: number | null | undefined, digits = 2) => formatNumber(value, { digits });
const optional = (form: FormData, name: string) =>
  form.get(name) === '' ? null : Number(form.get(name));
function resultShape(value: unknown): value is SimulationResult {
  return Boolean(
    value &&
    typeof value === 'object' &&
    'summary' in value &&
    'curve' in value &&
    Array.isArray(value.curve) &&
    'positions' in value,
  );
}
type Comparison = {
  items: Array<{
    id: number;
    name: string;
    from_date: string;
    to_date: string;
    return: number | null;
    benchmark_return: number | null;
    max_drawdown: number | null;
  }>;
};
function comparisonShape(value: unknown): value is Comparison {
  return Boolean(
    value && typeof value === 'object' && 'items' in value && Array.isArray(value.items),
  );
}
function Results({ value, currency }: { value: SimulationResult; currency: string }) {
  const gain = typeof value.summary.return === 'number' ? value.summary.return : null;
  const spy =
    typeof value.summary.benchmark_return === 'number' ? value.summary.benchmark_return : null;
  const total = typeof value.summary.value === 'number' ? value.summary.value : null;
  return (
    <section className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">
        Resultado simulado <Badge variant="outline">Experimental</Badge>
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">{value.note}</p>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <p>
          Valor:{' '}
          <strong>
            {number(total)} {currency}
          </strong>
        </p>
        <p>
          Retorno: <strong>{gain == null ? '—' : number(gain * 100) + ' %'}</strong>
        </p>
        <p>
          SPY: <strong>{spy == null ? '—' : number(spy * 100) + ' %'}</strong>
        </p>
      </div>
      {value.curve.length > 0 && (
        <Suspense fallback={<p>Preparando gráfico…</p>}>
          <SimulationChart curve={value.curve} />
        </Suspense>
      )}
      <p className="text-xs text-muted-foreground">
        Efectivo {number(value.cash)} {currency} · últimas {value.curve.length} sesiones de la
        curva.
      </p>
    </section>
  );
}

/** «Faltan precios de X»: the explicit download of that ticker (with SPY and FX), then the same trade. */
function MissingPrices({
  portfolioId,
  trade,
  retry,
}: {
  portfolioId: number;
  trade: SimulationTradeCreate;
  retry: () => void;
}) {
  const { start, job } = useJob('sim-prices');
  const status = job.data?.status;
  const running = start.isPending || status === 'queued' || status === 'running';
  // The trade is retried once per finished download, never on later renders.
  const retriedFor = useRef<string | null>(null);
  const finished = status === 'succeeded' ? job.data?.id : undefined;
  useEffect(() => {
    if (finished && retriedFor.current !== finished) {
      retriedFor.current = finished;
      retry();
    }
  }, [finished, retry]);
  const symbol = trade.symbol.trim().toUpperCase();
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg border bg-secondary/40 p-3 text-sm">
      <Button
        type="button"
        variant="outline"
        disabled={running}
        onClick={() =>
          start.mutate({ kind: 'sim_prices', portfolio_id: portfolioId, symbols: [symbol] })
        }
      >
        Descargar precios de {symbol} y registrar
      </Button>
      <span className="text-muted-foreground">
        {running
          ? 'Descargando de Yahoo Finance…'
          : status === 'failed'
            ? 'La descarga ha fallado; revisa su causa en Trabajos.'
            : 'Descarga explícita del histórico del ticker, SPY y los cambios de divisa.'}
      </span>
    </div>
  );
}

function Workspace({ portfolio }: { portfolio: SimulationPortfolio }) {
  const client = useQueryClient();
  const id = portfolio.id;
  const [pending, setPending] = useState<SimulationTradeCreate | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const trades = useQuery({
    queryKey: ['portfolio', 'simulations', id, 'trades'],
    queryFn: ({ signal }) => getSimulationTrades(id, signal),
  });
  const result = useQuery({
    queryKey: ['portfolio', 'simulations', id, 'result'],
    queryFn: ({ signal }) => getSimulationResult(id, signal),
    // Shown on opening the portfolio (#192): a read of the cache, as long as it has trades.
    enabled: (trades.data?.items.length ?? 0) > 0,
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const jobResult = useQuery({
    queryKey: ['job-result', jobId],
    queryFn: ({ signal }) => getJobResult(jobId!, signal),
    enabled: job.data?.status === 'succeeded',
  });
  const trade = useFormDefaults().data?.simulation_trade;
  const add = useMutation({
    mutationFn: (body: SimulationTradeCreate) => createSimulationTrade(id, body),
    onSuccess: () => {
      setPending(null);
      void client.invalidateQueries({ queryKey: ['portfolio', 'simulations', id] });
    },
  });
  const missing =
    add.error instanceof ApiError && add.error.code === 'prices_missing' ? pending : null;
  const undo = useMutation({
    mutationFn: () => undoSimulationTrade(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['portfolio', 'simulations', id] });
    },
  });
  const queue = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'sim_result',
        portfolio_id: id,
        idempotency_key: 'sim:' + id + ':' + crypto.randomUUID(),
      }),
    onSuccess: (queued) => setJobId(queued.id),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: SimulationTradeCreate = {
      symbol: String(form.get('symbol') ?? ''),
      asset_type: String(form.get('asset_type')) as 'STOCK' | 'ETF',
      side: String(form.get('side')) as 'BUY' | 'SELL',
      requested_date: String(form.get('requested_date')),
      notional: Number(form.get('notional')),
      // Empty: the backend infers them from the ticker's suffix (#192).
      market: (String(form.get('market') ?? '') || null) as SimulationTradeCreate['market'],
      quote_currency: (String(form.get('quote_currency') ?? '') ||
        null) as SimulationTradeCreate['quote_currency'],
      commission: optional(form, 'commission'),
      spread_bps: optional(form, 'spread_bps'),
      fx_rate: optional(form, 'fx_rate'),
      fx_fee_bps: Number(form.get('fx_fee_bps')),
    };
    setPending(body);
    add.mutate(body);
  }
  const displayed = resultShape(jobResult.data) ? jobResult.data : result.data;
  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-xl font-semibold">
          {portfolio.name} <Badge variant="outline">Experimental</Badge>
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Inicial {number(portfolio.initial_cash)} {portfolio.base_currency} · comisión acción{' '}
          {number(portfolio.stock_commission)} · ETF {number(portfolio.etf_commission)} · spread{' '}
          {number(portfolio.spread_bps)} pb.
        </p>
      </section>
      <SimulationPrices portfolioId={id} hasTrades={(trades.data?.items.length ?? 0) > 0} />
      {!trade && <LoadingState />}
      {trade && (
        <form onSubmit={submit} className="rounded-xl border bg-card p-5">
          <h2 className="text-lg font-semibold">Registrar operación simulada</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Se usa el cierre de la primera sesión. Mercado y divisa salen del ticker (AAPL o BRK.B
            en EE. UU.; SAP.DE, BP.L, SAN.MC o MC.PA en Europa) y los costes, de la cartera. Si
            faltan precios, se ofrece descargarlos sin salir de aquí.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <label className="text-sm">
              Símbolo
              <Input className="mt-1" name="symbol" required maxLength={20} placeholder="AAPL" />
            </label>
            <label className="text-sm">
              Lado
              <NativeSelect name="side" className="mt-1 w-full" defaultValue={trade.side}>
                <option value="BUY">Comprar</option>
                <option value="SELL">Vender</option>
              </NativeSelect>
            </label>
            <label className="text-sm">
              Fecha
              <Input className="mt-1" name="requested_date" type="date" required />
            </label>
            <label className="text-sm">
              Importe cotizado
              <Input
                className="mt-1"
                name="notional"
                type="number"
                min={0.01}
                step="0.01"
                required
              />
            </label>
          </div>
          <AdvancedOptions id="operacion-simulada" className="mt-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <HelpField
                id="trade-asset"
                label="Instrumento"
                help="Acción o ETF: decide qué comisión de la cartera se aplica."
              >
                <NativeSelect
                  id="trade-asset"
                  name="asset_type"
                  className="mt-1 w-full"
                  defaultValue={trade.asset_type}
                >
                  <option value="STOCK">Acción</option>
                  <option value="ETF">ETF</option>
                </NativeSelect>
              </HelpField>
              <HelpField
                id="trade-market"
                label="Mercado"
                help="Bolsa (código ISO 10383) cuyo calendario fija la primera sesión de cierre."
              >
                <NativeSelect
                  id="trade-market"
                  name="market"
                  className="mt-1 w-full"
                  defaultValue={trade.market ?? ''}
                >
                  <option value="">Automático, según el ticker</option>
                  {['XNYS', 'XETR', 'XLON', 'XMAD', 'XPAR'].map((market) => (
                    <option key={market}>{market}</option>
                  ))}
                </NativeSelect>
              </HelpField>
              <HelpField
                id="trade-currency"
                label="Divisa cotizada"
                help="Divisa del importe y del precio. Si no es la base de la cartera, se convierte."
              >
                <NativeSelect
                  id="trade-currency"
                  name="quote_currency"
                  className="mt-1 w-full"
                  defaultValue={trade.quote_currency ?? ''}
                >
                  <option value="">Automática, según el mercado</option>
                  <option>USD</option>
                  <option>EUR</option>
                  <option>GBP</option>
                </NativeSelect>
              </HelpField>
              <HelpField
                id="trade-fx"
                label="Cambio manual (opcional)"
                help="Unidades de la divisa base por unidad cotizada. Vacío: el cambio de la caché de ese día."
              >
                <Input
                  id="trade-fx"
                  className="mt-1"
                  name="fx_rate"
                  type="number"
                  min={0.000001}
                  step="0.000001"
                />
              </HelpField>
              <HelpField
                id="trade-commission"
                label="Comisión (opcional)"
                help="En la divisa cotizada. Vacío: la comisión de la cartera para ese instrumento."
              >
                <Input
                  id="trade-commission"
                  className="mt-1"
                  name="commission"
                  type="number"
                  min={0}
                  step="0.01"
                />
              </HelpField>
              <HelpField
                id="trade-spread"
                label="Spread pb (opcional)"
                help="Puntos básicos (1 pb = 0,01 %) que empeoran el precio. Vacío: el de la cartera."
              >
                <Input
                  id="trade-spread"
                  className="mt-1"
                  name="spread_bps"
                  type="number"
                  min={0}
                  step="0.1"
                />
              </HelpField>
              <HelpField
                id="trade-fx-fee"
                label="Coste cambio pb"
                help="Puntos básicos cobrados al convertir divisa; 0 si no hay conversión."
              >
                <Input
                  id="trade-fx-fee"
                  className="mt-1"
                  name="fx_fee_bps"
                  type="number"
                  min={0}
                  step="0.1"
                  defaultValue={trade.fx_fee_bps}
                  required
                />
              </HelpField>
            </div>
          </AdvancedOptions>
          <Button className="mt-4" type="submit" disabled={add.isPending}>
            Registrar operación
          </Button>
          {add.isError && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {add.error.message}
            </p>
          )}
          {missing && (
            <MissingPrices portfolioId={id} trade={missing} retry={() => add.mutate(missing)} />
          )}
          {add.isSuccess && (
            <p role="status" className="mt-2 text-sm">
              Operación registrada.
            </p>
          )}
        </form>
      )}
      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Operaciones</h2>
        {trades.isPending && <LoadingState />}
        {trades.isError && <ErrorState error={trades.error} retry={() => void trades.refetch()} />}
        {trades.data?.items.length === 0 && <p className="mt-3 text-sm">Sin operaciones.</p>}
        <ul className="mt-3 divide-y">
          {trades.data?.items.map((trade) => (
            <li key={trade.id} className="flex flex-wrap justify-between gap-2 py-3 text-sm">
              <span>
                {dateText(trade.execution_date)} · {trade.side} · {trade.symbol}
              </span>
              <span>
                {number(trade.notional)} {trade.quote_currency} · comisión{' '}
                {number(trade.commission)}
              </span>
            </li>
          ))}
        </ul>
        {Boolean(trades.data?.items.length) && (
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            disabled={undo.isPending}
            onClick={() => undo.mutate()}
          >
            Deshacer última operación
          </Button>
        )}
        {undo.isError && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {undo.error.message}
          </p>
        )}
      </section>
      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Evolución y costes</h2>
        {!trades.data?.items.length && (
          <p className="mt-3 text-sm text-muted-foreground">
            El resultado frente a SPY aparece aquí en cuanto registres una operación.
          </p>
        )}
        {result.isFetching && !result.data && <LoadingState />}
        {result.isError &&
          !(result.error instanceof ApiError && result.error.code === 'job_required') && (
            <ErrorState error={result.error} retry={() => void result.refetch()} />
          )}
        {result.error instanceof ApiError && result.error.code === 'job_required' && (
          <div className="mt-3">
            <p className="text-sm">{result.error.message}</p>
            <Button
              className="mt-2"
              type="button"
              disabled={queue.isPending}
              onClick={() => queue.mutate()}
            >
              Encolar cálculo largo
            </Button>
            {queue.isError && (
              <p role="alert" className="text-sm text-destructive">
                {queue.error.message}
              </p>
            )}
          </div>
        )}
        {jobId && (
          <p role="status" className="mt-3 text-sm">
            Job {jobId.slice(0, 8)}: {job.data?.status ?? 'en espera'}.
            {job.data?.status === 'failed' && ' Revisa su actividad en Administración.'}
          </p>
        )}
        {jobResult.isError && (
          <p role="alert" className="text-sm text-destructive">
            {jobResult.error.message}
          </p>
        )}
      </section>
      {displayed && <Results value={displayed} currency={portfolio.base_currency ?? 'USD'} />}
    </div>
  );
}

export function SimulationsPage() {
  const client = useQueryClient();
  const [compareJobId, setCompareJobId] = useState<string | null>(null);
  const compareJob = useQuery({
    queryKey: ['job', compareJobId],
    queryFn: ({ signal }) => getJob(compareJobId!, signal),
    enabled: compareJobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const compareResult = useQuery({
    queryKey: ['job-result', compareJobId],
    queryFn: ({ signal }) => getJobResult(compareJobId!, signal),
    enabled: compareJob.data?.status === 'succeeded',
  });
  const compare = useMutation({
    mutationFn: () =>
      createJob({ kind: 'sim_compare', idempotency_key: 'sim-compare:' + crypto.randomUUID() }),
    onSuccess: (queued) => setCompareJobId(queued.id),
  });
  const portfolios = useQuery({
    queryKey: ['portfolio', 'simulations'],
    queryFn: ({ signal }) => getSimulations(signal),
  });
  const [active, setActive] = useState<number | null>(null);
  const simulation = useFormDefaults().data?.simulation;
  const current =
    portfolios.data?.items.find((item) => item.id === active) ?? portfolios.data?.items[0];
  const create = useMutation({
    mutationFn: createSimulation,
    onSuccess: (item) => {
      setActive(item.id);
      void client.invalidateQueries({ queryKey: ['portfolio', 'simulations'] });
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      name: String(form.get('name') ?? ''),
      initial_cash: Number(form.get('initial_cash')),
      base_currency: String(form.get('base_currency')) as 'USD' | 'EUR',
      stock_commission: Number(form.get('stock_commission')),
      etf_commission: Number(form.get('etf_commission')),
      spread_bps: Number(form.get('spread_bps')),
    });
  }
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/cartera', label: 'Cartera' }}
        title="Carteras simuladas"
        description={
          <>
            Operaciones hipotéticas con costes y divisas. No se envían órdenes ni se descargan
            precios al abrir la pantalla.
          </>
        }
      />
      <details className="rounded-xl border bg-card p-5">
        <summary className="cursor-pointer font-semibold">Crear cartera simulada</summary>
        {!simulation && <LoadingState />}
        {simulation && (
          <form onSubmit={submit} className="mt-5 grid gap-3 sm:grid-cols-3">
            <label className="text-sm">
              Nombre
              <Input name="name" className="mt-1" maxLength={80} required />
            </label>
            <label className="text-sm">
              Capital inicial
              <Input
                name="initial_cash"
                className="mt-1"
                type="number"
                min={1}
                step="0.01"
                defaultValue={simulation.initial_cash}
                required
              />
            </label>
            <label className="text-sm">
              Divisa base
              <NativeSelect
                name="base_currency"
                className="mt-1 w-full"
                defaultValue={simulation.base_currency}
              >
                <option>USD</option>
                <option>EUR</option>
              </NativeSelect>
            </label>
            <AdvancedOptions id="crear-simulada" className="sm:col-span-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <HelpField
                  id="sim-stock-commission"
                  label="Comisión acción"
                  help="Importe fijo por operación con acciones, en la divisa cotizada."
                >
                  <Input
                    id="sim-stock-commission"
                    name="stock_commission"
                    className="mt-1"
                    type="number"
                    min={0}
                    step="0.01"
                    defaultValue={simulation.stock_commission}
                    required
                  />
                </HelpField>
                <HelpField
                  id="sim-etf-commission"
                  label="Comisión ETF"
                  help="Importe fijo por operación con ETF, en la divisa cotizada."
                >
                  <Input
                    id="sim-etf-commission"
                    name="etf_commission"
                    className="mt-1"
                    type="number"
                    min={0}
                    step="0.01"
                    defaultValue={simulation.etf_commission}
                    required
                  />
                </HelpField>
                <HelpField
                  id="sim-spread"
                  label="Spread pb"
                  help="Puntos básicos (1 pb = 0,01 %) que empeoran cada precio de compra y venta."
                >
                  <Input
                    id="sim-spread"
                    name="spread_bps"
                    className="mt-1"
                    type="number"
                    min={0}
                    step="0.1"
                    defaultValue={simulation.spread_bps}
                    required
                  />
                </HelpField>
              </div>
            </AdvancedOptions>
            <Button className="w-fit" type="submit" disabled={create.isPending}>
              Crear cartera
            </Button>
            {create.isError && (
              <p role="alert" className="text-sm text-destructive">
                {create.error.message}
              </p>
            )}
          </form>
        )}
      </details>
      {portfolios.isPending && <LoadingState />}
      {portfolios.isError && (
        <ErrorState error={portfolios.error} retry={() => void portfolios.refetch()} />
      )}
      {portfolios.data?.items.length === 0 && (
        <p className="text-sm">Crea una cartera para empezar.</p>
      )}
      {current && (
        <>
          <label className="block text-sm font-medium">
            Cartera activa
            <NativeSelect
              className="mt-1 w-full max-w-sm"
              value={current.id}
              onChange={(event) => setActive(Number(event.target.value))}
            >
              {portfolios.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} (#{item.id})
                </option>
              ))}
            </NativeSelect>
          </label>
          <Workspace key={current.id} portfolio={current} />
        </>
      )}
      {portfolios.data && portfolios.data.items.length > 0 && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="text-lg font-semibold">Comparar carteras</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Cada cartera conserva su propio periodo y sus costes; comparar retornos de periodos
            distintos no valida una estrategia.
          </p>
          <Button
            className="mt-4"
            type="button"
            variant="outline"
            disabled={compare.isPending}
            onClick={() => compare.mutate()}
          >
            Calcular comparación
          </Button>
          {compare.isError && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {compare.error.message}
            </p>
          )}
          {compareJobId && (
            <p role="status" className="mt-2 text-sm">
              Job de comparación: {compareJob.data?.phase ?? 'En espera'}.
            </p>
          )}
          {compareJob.data?.status === 'failed' && (
            <p className="mt-2 text-sm text-destructive">
              No se completó la comparación; revisa Administración.
            </p>
          )}
          {compareResult.isError && (
            <ErrorState error={compareResult.error} retry={() => void compareResult.refetch()} />
          )}
          {comparisonShape(compareResult.data) &&
            (compareResult.data.items.length ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="border-b">
                    <tr>
                      <th className="py-2">Cartera</th>
                      <th>Desde</th>
                      <th>Hasta</th>
                      <th>Retorno</th>
                      <th>SPY</th>
                      <th>Drawdown</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareResult.data.items.map((row) => (
                      <tr key={row.id} className="border-b last:border-0">
                        <td className="py-2">{row.name}</td>
                        <td>{dateText(row.from_date)}</td>
                        <td>{dateText(row.to_date)}</td>
                        <td>{row.return == null ? '—' : number(row.return * 100) + ' %'}</td>
                        <td>
                          {row.benchmark_return == null
                            ? '—'
                            : number(row.benchmark_return * 100) + ' %'}
                        </td>
                        <td>
                          {row.max_drawdown == null ? '—' : number(row.max_drawdown * 100) + ' %'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-3 text-sm">Aún no hay carteras con resultados completos.</p>
            ))}
        </section>
      )}
    </div>
  );
}
