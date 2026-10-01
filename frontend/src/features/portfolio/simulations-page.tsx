import { lazy, Suspense, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
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
import { Input } from '@/shared/ui/input';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Badge } from '@/shared/ui/badge';
import { SimulationPrices } from './sim-prices';

const SimulationChart = lazy(() => import('./simulation-chart'));
const number = (value: number | null | undefined, digits = 2) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value);
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

function Workspace({ portfolio }: { portfolio: SimulationPortfolio }) {
  const client = useQueryClient();
  const id = portfolio.id;
  const [showResult, setShowResult] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const trades = useQuery({
    queryKey: ['portfolio', 'simulations', id, 'trades'],
    queryFn: ({ signal }) => getSimulationTrades(id, signal),
  });
  const result = useQuery({
    queryKey: ['portfolio', 'simulations', id, 'result'],
    queryFn: ({ signal }) => getSimulationResult(id, signal),
    enabled: showResult,
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
  const add = useMutation({
    mutationFn: (body: SimulationTradeCreate) => createSimulationTrade(id, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['portfolio', 'simulations', id] });
      setShowResult(false);
    },
  });
  const undo = useMutation({
    mutationFn: () => undoSimulationTrade(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['portfolio', 'simulations', id] });
      setShowResult(false);
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
    add.mutate({
      symbol: String(form.get('symbol') ?? ''),
      asset_type: String(form.get('asset_type')) as 'STOCK' | 'ETF',
      side: String(form.get('side')) as 'BUY' | 'SELL',
      requested_date: String(form.get('requested_date')),
      notional: Number(form.get('notional')),
      market: String(form.get('market')) as SimulationTradeCreate['market'],
      quote_currency: String(form.get('quote_currency')) as SimulationTradeCreate['quote_currency'],
      commission: optional(form, 'commission'),
      spread_bps: optional(form, 'spread_bps'),
      fx_rate: optional(form, 'fx_rate'),
      fx_fee_bps: Number(form.get('fx_fee_bps')),
    });
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
      <form onSubmit={submit} className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Registrar operación simulada</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Se usa el cierre de la primera sesión. Si faltan precios o cambio en caché, se rechaza sin
          guardar. Actualiza sus precios en «Precios públicos», más arriba.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm">
            Símbolo
            <Input className="mt-1" name="symbol" required maxLength={20} />
          </label>
          <label className="text-sm">
            Instrumento
            <select
              name="asset_type"
              className="mt-1 h-9 w-full rounded-md border bg-background px-2"
            >
              <option value="STOCK">Acción</option>
              <option value="ETF">ETF</option>
            </select>
          </label>
          <label className="text-sm">
            Lado
            <select name="side" className="mt-1 h-9 w-full rounded-md border bg-background px-2">
              <option value="BUY">Comprar</option>
              <option value="SELL">Vender</option>
            </select>
          </label>
          <label className="text-sm">
            Fecha
            <Input className="mt-1" name="requested_date" type="date" required />
          </label>
          <label className="text-sm">
            Importe cotizado
            <Input className="mt-1" name="notional" type="number" min={0.01} step="0.01" required />
          </label>
          <label className="text-sm">
            Mercado
            <select name="market" className="mt-1 h-9 w-full rounded-md border bg-background px-2">
              {['XNYS', 'XETR', 'XLON', 'XMAD', 'XPAR'].map((market) => (
                <option key={market}>{market}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Divisa cotizada
            <select
              name="quote_currency"
              className="mt-1 h-9 w-full rounded-md border bg-background px-2"
            >
              <option>USD</option>
              <option>EUR</option>
              <option>GBP</option>
            </select>
          </label>
          <label className="text-sm">
            Cambio manual (opcional)
            <Input className="mt-1" name="fx_rate" type="number" min={0.000001} step="0.000001" />
          </label>
          <label className="text-sm">
            Comisión (opcional)
            <Input className="mt-1" name="commission" type="number" min={0} step="0.01" />
          </label>
          <label className="text-sm">
            Spread pb (opcional)
            <Input className="mt-1" name="spread_bps" type="number" min={0} step="0.1" />
          </label>
          <label className="text-sm">
            Coste cambio pb
            <Input
              className="mt-1"
              name="fx_fee_bps"
              type="number"
              min={0}
              step="0.1"
              defaultValue={0}
              required
            />
          </label>
        </div>
        <Button className="mt-4" type="submit" disabled={add.isPending}>
          Registrar operación
        </Button>
        {add.isError && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {add.error.message}
          </p>
        )}
        {add.isSuccess && (
          <p role="status" className="mt-2 text-sm">
            Operación registrada.
          </p>
        )}
      </form>
      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Operaciones</h2>
        {trades.isPending && <LoadingState />}
        {trades.isError && <ErrorState error={trades.error} retry={() => void trades.refetch()} />}
        {trades.data?.items.length === 0 && <p className="mt-3 text-sm">Sin operaciones.</p>}
        <ul className="mt-3 divide-y">
          {trades.data?.items.map((trade) => (
            <li key={trade.id} className="flex flex-wrap justify-between gap-2 py-3 text-sm">
              <span>
                {trade.execution_date} · {trade.side} · {trade.symbol}
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
        <Button
          className="mt-3"
          type="button"
          variant="outline"
          onClick={() => setShowResult(true)}
        >
          Calcular resultado
        </Button>
        {showResult && result.isPending && <LoadingState />}
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
      <header>
        <Link className="text-sm text-primary" to="/cartera">
          ← Cartera
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Carteras simuladas</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Operaciones hipotéticas con costes y divisas. No se envían órdenes ni se descargan precios
          al abrir la pantalla.
        </p>
      </header>
      <details className="rounded-xl border bg-card p-5">
        <summary className="cursor-pointer font-semibold">Crear cartera simulada</summary>
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
              defaultValue={10000}
              required
            />
          </label>
          <label className="text-sm">
            Divisa base
            <select
              name="base_currency"
              className="mt-1 h-9 w-full rounded-md border bg-background px-2"
            >
              <option>USD</option>
              <option>EUR</option>
            </select>
          </label>
          <label className="text-sm">
            Comisión acción
            <Input
              name="stock_commission"
              className="mt-1"
              type="number"
              min={0}
              step="0.01"
              defaultValue={1}
              required
            />
          </label>
          <label className="text-sm">
            Comisión ETF
            <Input
              name="etf_commission"
              className="mt-1"
              type="number"
              min={0}
              step="0.01"
              defaultValue={0}
              required
            />
          </label>
          <label className="text-sm">
            Spread pb
            <Input
              name="spread_bps"
              className="mt-1"
              type="number"
              min={0}
              step="0.1"
              defaultValue={10}
              required
            />
          </label>
          <Button className="w-fit" type="submit" disabled={create.isPending}>
            Crear cartera
          </Button>
          {create.isError && (
            <p role="alert" className="text-sm text-destructive">
              {create.error.message}
            </p>
          )}
        </form>
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
            <select
              className="mt-1 block h-9 w-full max-w-sm rounded-md border bg-background px-2"
              value={current.id}
              onChange={(event) => setActive(Number(event.target.value))}
            >
              {portfolios.data?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} (#{item.id})
                </option>
              ))}
            </select>
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
                        <td>{row.from_date}</td>
                        <td>{row.to_date}</td>
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
