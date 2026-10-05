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
import { CoverageWarnings } from './coverage-warnings';
import { SectionLinks } from '@/shared/ui/section-links';
import { GitCompareArrows, Globe, Radar } from 'lucide-react';
import { PageHeader } from '@/shared/ui/page-header';
import { DataTable } from '@/shared/ui/data-table';
import { RankCell, RankLegend } from '@/shared/ui/rank-cell';
import { Term } from '@/shared/ui/term';

/** 0-100 points (score, coverage or a sector percentile, 100 = best) as a 0..1 colour position. */
const score = (value: number | null | undefined) => (value == null ? null : value / 100);

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
      <div className="mb-7">
        <PageHeader
          eyebrow="Mercado / Screener"
          title="Explora el universo"
          description="Compara empresas con los datos y el modelo de tu instalación local."
          actions={
            <Button
              variant="outline"
              disabled={result.isFetching}
              onClick={() => void result.refetch()}
            >
              <RotateCw className={result.isFetching ? 'animate-spin' : ''} aria-hidden="true" />
              Consultar caché
            </Button>
          }
        >
          <SectionLinks
            label="Apartados de Mercado"
            links={[
              {
                to: '/mercado/comparar',
                label: 'Comparar empresas',
                description: 'De dos a cinco, lado a lado',
                icon: GitCompareArrows,
              },
              {
                to: '/mercado/macro',
                label: 'Panel macro',
                description: 'Tipos, inflación, curva y crédito',
                icon: Globe,
              },
              {
                to: '/mercado/senales',
                label: 'Signal Monitor',
                description: 'Rankings guardados y cambios',
                icon: Radar,
              },
            ]}
          />
        </PageHeader>
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
      <CoverageWarnings />
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
        <div>
          <LoadingState />
          <p className="mt-2 text-center text-sm text-muted-foreground">
            Calculando el ranking con tu caché local. Si GABI acaba de arrancar o han cambiado los
            datos, la primera consulta tarda entre unos 20 s y un minuto; después es inmediata.
          </p>
        </div>
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
              <>
                <DataTable label="Tabla desplazable">
                  <table className="w-full text-left text-sm sm:min-w-[770px]">
                    <caption className="sr-only">
                      Ranking del modelo local. Posición global antes de filtros.
                    </caption>
                    <thead className="bg-muted/60 text-xs text-muted-foreground">
                      <tr>
                        <th scope="col" className="p-2 sm:p-4 sm:pl-5">
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
                            className={
                              'p-2 sm:p-4' +
                              (key === 'name' ? '' : ' num') +
                              (key === 'name' || key === 'composite_score'
                                ? ''
                                : ' hidden sm:table-cell')
                            }
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
                          <td className="p-2 text-xs tabular-nums text-muted-foreground sm:p-4 sm:pl-5">
                            {row.rank}
                          </td>
                          <th scope="row" className="max-w-72 p-2 font-normal sm:p-4">
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
                            <details className="mt-2 text-xs sm:hidden">
                              <summary className="cursor-pointer text-primary">
                                Más métricas de {row.symbol}
                              </summary>
                              <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-foreground">
                                <dt>Precio USD</dt>
                                <dd className="text-right">{metric(row.metrics.price)}</dd>
                                <dt>Cobertura</dt>
                                <dd className="text-right">{metric(row.metrics.confidence)}</dd>
                                <dt>Capitalización</dt>
                                <dd className="text-right">
                                  {metric(row.metrics.market_cap, true)}
                                </dd>
                                <dt>PER</dt>
                                <dd className="text-right">{metric(row.metrics.pe)}</dd>
                              </dl>
                            </details>
                          </th>
                          <td className="num hidden whitespace-nowrap p-4 sm:table-cell">
                            {metric(row.metrics.price)}
                          </td>
                          <RankCell
                            className="num p-2 font-semibold sm:p-4"
                            position={score(row.metrics.composite_score?.value)}
                            scope="del universo"
                          >
                            {metric(row.metrics.composite_score)}
                          </RankCell>
                          <RankCell
                            className="num hidden p-4 sm:table-cell"
                            position={score(row.metrics.confidence?.value)}
                            scope="del universo"
                          >
                            {metric(row.metrics.confidence)}
                          </RankCell>
                          <td className="num hidden whitespace-nowrap p-4 sm:table-cell">
                            {metric(row.metrics.market_cap, true)}
                          </td>
                          <RankCell
                            className="num hidden p-4 sm:table-cell"
                            position={score(row.metrics.pe_pct?.value)}
                            scope="de su sector"
                          >
                            {metric(row.metrics.pe)}
                          </RankCell>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </DataTable>
                <div className="px-5 pb-1">
                  <RankLegend>
                    <Term k="composite_score">Score</Term> y{' '}
                    <Term k="confidence">cobertura ponderada</Term> de 0 (rojo) a 100 (verde). El
                    PER se colorea por su <Term k="percentile">percentil dentro del sector</Term>:
                    verde es un PER bajo frente a sus comparables, no un PER bajo en absoluto.
                  </RankLegend>
                </div>
              </>
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
