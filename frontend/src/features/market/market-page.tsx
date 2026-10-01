import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Search,
  SlidersHorizontal,
  RotateCw,
} from 'lucide-react';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect } from '@/shared/ui/native-select';
import { LoadingState, ErrorState, EmptyState } from '@/shared/ui/resource-state';
import { metric, dateLabel } from '@/shared/lib/format';
import { useRanking } from './queries';
import { rankingParams, patchParams, sortOptions, type SortKey } from './params';
import { Evidence } from './evidence';
import { RankingEvidence, RankingStabilityPanel } from './candidate-evidence';

export function MarketPage() {
  const [params, setParams] = useSearchParams();
  const query = rankingParams(params);
  const result = useRanking(query);
  const data = result.data;
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setParams(
      patchParams(params, {
        search: String(form.get('search') ?? '').trim(),
        sectors: form.getAll('sectors').map(String).filter(Boolean),
        min_market_cap: String(form.get('min_market_cap') ?? ''),
        golden_cross_only: form.has('golden_cross_only') ? 'true' : null,
        hide_no_data: form.has('hide_no_data') ? null : 'false',
      }),
    );
  }
  function sort(key: SortKey) {
    setParams(
      patchParams(params, {
        order_by: key,
        direction: query.order_by === key && query.direction === 'desc' ? 'asc' : 'desc',
      }),
    );
  }
  return (
    <>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Mercado / Screener
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Explora el universo</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Compara empresas con los datos y el modelo de tu instalación local.
          </p>
          <Link
            className="mt-3 inline-block text-sm font-medium text-primary underline"
            to="/mercado/comparar"
          >
            Comparar empresas →
          </Link>
          <Link
            className="ml-4 inline-block text-sm font-medium text-primary underline"
            to="/mercado/macro"
          >
            Panel macro →
          </Link>
          <Link
            className="ml-4 inline-block text-sm font-medium text-primary underline"
            to="/mercado/senales"
          >
            Signal Monitor →
          </Link>
        </div>
        <Button
          variant="outline"
          disabled={result.isFetching}
          onClick={() => void result.refetch()}
        >
          <RotateCw className={result.isFetching ? 'animate-spin' : ''} aria-hidden="true" />
          Consultar caché
        </Button>
      </div>
      {data && <Evidence model={data.model} data={data.data} />}
      {data && (
        <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            ['Universo local', String(data.data.universe_count), 'Empresas en la caché'],
            ['Con score', String(data.data.scored_count), 'Modelo ' + data.model.model_id],
            [
              'Precios disponibles',
              String(data.data.prices_available),
              'Último: ' + dateLabel(data.data.latest_price_date),
            ],
            [
              'Fundamentales',
              String(data.data.fundamentals_available),
              data.data.sec_available + ' con información SEC',
            ],
          ].map(([label, value, detail]) => (
            <div key={label} className="rounded-xl border bg-card p-5">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="my-2 text-2xl font-semibold tabular-nums">{value}</p>
              <p className="break-words text-xs text-muted-foreground">{detail}</p>
            </div>
          ))}
        </div>
      )}
      <section aria-label="Filtros del ranking" className="mb-5 rounded-xl border bg-card p-4">
        <form key={params.toString()} onSubmit={filter} className="space-y-3">
          <div className="grid items-end gap-3 sm:grid-cols-2 xl:grid-cols-[2fr_1.3fr_1fr_auto]">
            <div>
              <label className="mb-1.5 block text-xs font-medium" htmlFor="search">
                Buscar empresa o símbolo
              </label>
              <div className="relative">
                <Search
                  size={16}
                  className="pointer-events-none absolute left-3 top-3 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  id="search"
                  name="search"
                  maxLength={100}
                  defaultValue={query.search}
                  placeholder="Ej. Apple, AAPL…"
                  className="h-10 pl-9"
                />
              </div>
            </div>
            <div>
              <p id="sector-label" className="mb-1.5 text-xs font-medium">
                Sectores
              </p>
              <details className="relative">
                <summary
                  aria-labelledby="sector-label sector-selection"
                  className="flex h-10 cursor-pointer items-center justify-between rounded-md border px-3 text-sm"
                >
                  <span id="sector-selection">
                    {query.sectors?.length
                      ? query.sectors.length + ' seleccionados'
                      : 'Todos los sectores'}
                  </span>
                  <ChevronRight size={14} aria-hidden="true" />
                </summary>
                <fieldset className="absolute left-0 top-12 z-20 max-h-64 w-full min-w-56 space-y-1 overflow-y-auto rounded-lg border bg-card p-3 shadow-lg">
                  <legend className="sr-only">Seleccionar sectores</legend>
                  <p className="mb-2 text-xs text-muted-foreground">
                    Sin selección se incluyen todos.
                  </p>
                  {Array.from(new Set([...(data?.sectors ?? []), ...(query.sectors ?? [])])).map(
                    (s) => (
                      <label
                        className="flex cursor-pointer items-center gap-2 rounded p-2 text-xs hover:bg-muted"
                        key={s}
                      >
                        <input
                          type="checkbox"
                          name="sectors"
                          value={s}
                          defaultChecked={query.sectors?.includes(s)}
                          className="size-4 accent-primary"
                        />
                        {s}
                      </label>
                    ),
                  )}
                </fieldset>
              </details>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium" htmlFor="cap">
                Capitalización mínima · USD
              </label>
              <Input
                id="cap"
                type="number"
                name="min_market_cap"
                min={0}
                max={1e15}
                step="any"
                defaultValue={query.min_market_cap || ''}
                placeholder="Sin mínimo"
                className="h-10"
              />
            </div>
            <Button type="submit" className="h-10">
              <SlidersHorizontal aria-hidden="true" />
              Aplicar filtros
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-xs">
            <label className="flex items-center gap-2">
              <input
                name="hide_no_data"
                type="checkbox"
                defaultChecked={query.hide_no_data}
                className="size-4 accent-primary"
              />
              Ocultar empresas sin datos
            </label>
            <label className="flex items-center gap-2">
              <input
                name="golden_cross_only"
                type="checkbox"
                defaultChecked={query.golden_cross_only}
                className="size-4 accent-primary"
              />
              Solo cruce dorado reciente
            </label>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={() => setParams(new URLSearchParams())}
            >
              Restablecer
            </Button>
          </div>
        </form>
      </section>
      {result.isPending ? (
        <LoadingState />
      ) : result.isError ? (
        <ErrorState error={result.error} retry={() => void result.refetch()} />
      ) : (
        data && (
          <section
            aria-label="Ranking de empresas"
            className="overflow-hidden rounded-xl border bg-card"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
              <div>
                <h2 className="font-semibold">
                  Ranking de empresas{' '}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {data.total} resultados
                  </span>
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Score en puntos de 0 a 100 · cobertura de métricas, no probabilidad de acierto. —
                  significa dato ausente.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <label htmlFor="sort" className="text-xs">
                  Ordenar por
                </label>
                <NativeSelect
                  id="sort"
                  value={query.order_by}
                  onChange={(e) => setParams(patchParams(params, { order_by: e.target.value }))}
                >
                  {sortOptions.map((o) => (
                    <option key={o.key} value={o.key}>
                      {o.label}
                    </option>
                  ))}
                </NativeSelect>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={query.direction === 'desc' ? 'Orden ascendente' : 'Orden descendente'}
                  onClick={() =>
                    setParams(
                      patchParams(params, {
                        direction: query.direction === 'desc' ? 'asc' : 'desc',
                      }),
                    )
                  }
                >
                  {query.direction === 'desc' ? (
                    <ArrowDown aria-hidden="true" />
                  ) : (
                    <ArrowUp aria-hidden="true" />
                  )}
                </Button>
              </div>
            </div>
            {!data.items.length ? (
              <EmptyState filtered={data.data.status !== 'empty'} />
            ) : (
              <div className="overflow-x-auto" tabIndex={0} aria-label="Tabla desplazable">
                <table className="w-full min-w-[770px] text-left text-sm">
                  <caption className="sr-only">
                    Ranking del modelo local. Posición global antes de filtros.
                  </caption>
                  <thead className="bg-muted/60 text-xs text-muted-foreground">
                    <tr>
                      <th scope="col" className="p-4 pl-5">
                        Pos.
                      </th>
                      {(
                        [
                          ['name', 'Empresa'],
                          ['price', 'Precio · USD'],
                          ['composite_score', 'Score'],
                          ['confidence', 'Cobertura ponderada'],
                          ['market_cap', 'Capitalización'],
                          ['pe', 'PER'],
                        ] as const
                      ).map(([key, label]) => (
                        <th
                          scope="col"
                          key={key}
                          aria-sort={
                            query.order_by === key
                              ? query.direction === 'desc'
                                ? 'descending'
                                : 'ascending'
                              : 'none'
                          }
                          className="p-4"
                        >
                          <button
                            className="flex items-center gap-1 whitespace-nowrap"
                            onClick={() => sort(key)}
                          >
                            {label}
                            {query.order_by === key &&
                              (query.direction === 'desc' ? (
                                <ArrowDown size={12} aria-hidden="true" />
                              ) : (
                                <ArrowUp size={12} aria-hidden="true" />
                              ))}
                          </button>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((row) => (
                      <tr
                        key={row.symbol}
                        className="border-t transition-colors hover:bg-accent/35"
                      >
                        <td className="p-4 pl-5 text-xs tabular-nums text-muted-foreground">
                          {row.rank}
                        </td>
                        <th scope="row" className="max-w-72 p-4 font-normal">
                          <Link
                            to={
                              '/mercado/empresas/' +
                              encodeURIComponent(row.symbol) +
                              '?' +
                              params.toString()
                            }
                            className="inline-flex flex-col gap-1 rounded-sm"
                          >
                            <span className="font-semibold text-primary">
                              {row.symbol}
                              <span className="ml-2 font-normal text-foreground">
                                {row.name ?? 'Nombre no disponible'}
                              </span>
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {row.sector ?? 'Sin sector'}
                            </span>
                          </Link>
                        </th>
                        <td className="p-4 whitespace-nowrap tabular-nums">
                          {metric(row.metrics.price)}
                        </td>
                        <td className="p-4 tabular-nums">
                          <span className="rounded-md bg-secondary px-2 py-1 font-semibold">
                            {metric(row.metrics.composite_score)}
                          </span>
                        </td>
                        <td className="p-4 tabular-nums">{metric(row.metrics.confidence)}</td>
                        <td className="p-4 whitespace-nowrap tabular-nums">
                          {metric(row.metrics.market_cap, true)}
                        </td>
                        <td className="p-4 tabular-nums">{metric(row.metrics.pe)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t px-5 py-4 text-xs text-muted-foreground">
              <p>
                {data.total ? data.offset + 1 : 0}–{data.offset + data.items.length} de {data.total}{' '}
                · Consulta: {dateLabel(data.generated_at)}
              </p>
              <div className="flex items-center gap-2">
                <label htmlFor="page-size">Filas</label>
                <NativeSelect
                  id="page-size"
                  value={query.limit}
                  onChange={(e) => setParams(patchParams(params, { limit: e.target.value }))}
                >
                  {Array.from(new Set([10, 25, 50, 100, query.limit]))
                    .sort((a, b) => a - b)
                    .map((n) => (
                      <option value={n} key={n}>
                        {n}
                      </option>
                    ))}
                </NativeSelect>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Página anterior"
                  disabled={query.offset === 0}
                  onClick={() =>
                    setParams(
                      patchParams(
                        params,
                        { offset: String(Math.max(0, query.offset - query.limit)) },
                        false,
                      ),
                    )
                  }
                >
                  <ChevronLeft aria-hidden="true" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Página siguiente"
                  disabled={
                    data.offset + data.limit >= data.total || query.offset + query.limit > 1000
                  }
                  onClick={() =>
                    setParams(
                      patchParams(params, { offset: String(query.offset + query.limit) }, false),
                    )
                  }
                >
                  <ChevronRight aria-hidden="true" />
                </Button>
              </div>
            </div>
          </section>
        )
      )}
      {data && (
        <>
          <RankingEvidence />
          <RankingStabilityPanel />
        </>
      )}
    </>
  );
}
