import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Download,
  Search,
  SlidersHorizontal,
  RotateCw,
} from 'lucide-react';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect } from '@/shared/ui/native-select';
import { LoadingState, ErrorState, EmptyState } from '@/shared/ui/resource-state';
import { dateLabel } from '@/shared/lib/format';
import { useBlockEvidence, useRanking } from './queries';
import { rankingParams, patchParams, sortOptions, type SortKey } from './params';
import { Evidence } from './evidence';
import { RankingEvidence, RankingStabilityPanel } from './candidate-evidence';
import { CoverageWarnings } from './coverage-warnings';
import { FollowButton } from './follow-button';
import { SectionLinks } from '@/shared/ui/section-links';
import { GitCompareArrows, Globe, Radar } from 'lucide-react';
import { PageHeader } from '@/shared/ui/page-header';
import { DataTable } from '@/shared/ui/data-table';
import { RankCell, RankLegend } from '@/shared/ui/rank-cell';
import { Term } from '@/shared/ui/term';
import { BlockBars, SummaryText } from '@/shared/ui/score-summary';
import { UnevenEvidenceNote } from '@/shared/ui/block-evidence';
import {
  exportHref,
  keptQuery,
  loadPreferences,
  RANKING_COLUMNS,
  savePreferences,
  visibleColumns,
} from './ranking-columns';

const MAX_COMPARED = 5;

/** Companies ticked for Comparar; kept while the ranking is filtered or paged. */
function ComparePicks({ picked, clear }: { picked: string[]; clear: () => void }) {
  if (!picked.length) return null;
  const target = new URLSearchParams();
  picked.forEach((symbol) => target.append('symbols', symbol));
  return (
    <div
      role="region"
      aria-label="Empresas para comparar"
      className="flex flex-wrap items-center gap-3 border-b bg-accent/40 px-5 py-3 text-sm"
    >
      <span>
        Para comparar: <span className="font-semibold">{picked.join(', ')}</span>
        <span className="ml-1 text-xs text-muted-foreground">
          ({picked.length} de {MAX_COMPARED})
        </span>
      </span>
      {picked.length >= 2 ? (
        <Button asChild size="sm">
          <Link to={'/descubrir/comparar?' + target.toString()}>
            <GitCompareArrows aria-hidden="true" />
            Comparar {picked.length}
          </Link>
        </Button>
      ) : (
        <span className="text-xs text-muted-foreground">Marca al menos otra empresa.</span>
      )}
      <Button size="sm" variant="ghost" onClick={clear}>
        Quitar selección
      </Button>
    </div>
  );
}

export function MarketPage() {
  const [params, setParams] = useSearchParams();
  const query = rankingParams(params);
  const result = useRanking(query);
  const evidence = useBlockEvidence();
  const data = result.data;
  const [picked, setPicked] = useState<string[]>([]);
  const [saved] = useState(loadPreferences);
  const [chosen, setChosen] = useState(saved.columns);
  const columns = visibleColumns(chosen);
  // A bare /descubrir reopens the last filters, order and rows; a link with its own query wins.
  useEffect(() => {
    if (!params.toString() && saved.query)
      setParams(new URLSearchParams(saved.query), { replace: true });
    // Only on arrival: «Restablecer» must be able to clear them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    savePreferences({ columns: chosen, query: keptQuery(params) });
  }, [chosen, params]);
  function choose(key: string, on: boolean) {
    setChosen((current) =>
      on
        ? [...current.filter((item) => item !== key), key]
        : current.filter((item) => item !== key),
    );
  }
  function toggle(symbol: string) {
    setPicked((current) =>
      current.includes(symbol)
        ? current.filter((item) => item !== symbol)
        : current.length < MAX_COMPARED
          ? [...current, symbol]
          : current,
    );
  }
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setParams(
      patchParams(params, {
        search: String(form.get('search') ?? '').trim(),
        sectors: form.getAll('sectors').map(String).filter(Boolean),
        exclude_sectors: form.getAll('exclude_sectors').map(String).filter(Boolean),
        earnings: String(form.get('earnings') ?? '') || null,
        earnings_days: form.get('earnings') ? String(form.get('earnings_days') ?? '') : null,
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
                to: '/descubrir/comparar',
                label: 'Comparar empresas',
                description: 'De dos a cinco, lado a lado',
                icon: GitCompareArrows,
              },
              {
                to: '/macro',
                label: 'Panel macro',
                description: 'Tipos, inflación, curva y crédito',
                icon: Globe,
              },
              {
                to: '/eventos',
                label: 'Eventos',
                description: 'Cambios del ranking, filings y resultados',
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
            <details className="relative">
              <summary className="flex cursor-pointer items-center gap-1">
                Excluir sectores
                {query.exclude_sectors?.length ? ` (${query.exclude_sectors.length})` : ''}
                <ChevronRight size={12} aria-hidden="true" />
              </summary>
              <fieldset className="absolute left-0 top-6 z-20 max-h-64 w-56 space-y-1 overflow-y-auto rounded-lg border bg-card p-3 shadow-lg">
                <legend className="sr-only">Sectores excluidos</legend>
                {Array.from(
                  new Set([...(data?.sectors ?? []), ...(query.exclude_sectors ?? [])]),
                ).map((s) => (
                  <label
                    className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-muted"
                    key={s}
                  >
                    <input
                      type="checkbox"
                      name="exclude_sectors"
                      value={s}
                      defaultChecked={query.exclude_sectors?.includes(s)}
                      className="size-4 accent-primary"
                    />
                    {s}
                  </label>
                ))}
              </fieldset>
            </details>
            <label className="flex items-center gap-2">
              Resultados
              <NativeSelect name="earnings" defaultValue={query.earnings ?? ''} className="h-8">
                <option value="">Indiferente</option>
                <option value="only">Solo los que presentan</option>
                <option value="exclude">Excluir los que presentan</option>
              </NativeSelect>
              en los próximos
              <Input
                name="earnings_days"
                type="number"
                min={0}
                max={90}
                defaultValue={query.earnings_days}
                aria-label="Días hasta los resultados"
                className="h-8 w-16"
              />
              días
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
            datos, la primera consulta puede tardar. Las siguientes reutilizan la caché mientras
            siga vigente.
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
                  Score y cobertura ponderada en puntos de 0 a 100, no probabilidad de acierto. —
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
                <div className="flex flex-wrap items-center gap-3 border-b px-5 py-3 text-sm">
                  <details className="relative">
                    <summary className="flex h-9 cursor-pointer items-center gap-2 rounded-md border px-3">
                      <Columns3 size={14} aria-hidden="true" />
                      Columnas ({columns.length - 1} de {RANKING_COLUMNS.length - 1})
                    </summary>
                    <fieldset className="absolute left-0 top-11 z-20 max-h-80 w-64 space-y-1 overflow-y-auto rounded-lg border bg-card p-3 shadow-lg">
                      <legend className="sr-only">Columnas visibles</legend>
                      <p className="mb-2 text-xs text-muted-foreground">
                        Se recuerdan en este navegador. Empresa y Score siempre se muestran.
                      </p>
                      {RANKING_COLUMNS.filter((column) => !column.fixed).map((column) => (
                        <label
                          key={column.key}
                          className="flex cursor-pointer items-center gap-2 rounded p-2 text-xs hover:bg-muted"
                        >
                          <input
                            type="checkbox"
                            className="size-4 accent-primary"
                            checked={chosen.includes(column.key)}
                            onChange={(event) => choose(column.key, event.target.checked)}
                          />
                          {column.label}
                        </label>
                      ))}
                    </fieldset>
                  </details>
                  <Button asChild variant="outline" size="sm">
                    <a href={exportHref(params, columns)} download>
                      <Download aria-hidden="true" />
                      Exportar CSV ({data.total} filas)
                    </a>
                  </Button>
                </div>
                <ComparePicks picked={picked} clear={() => setPicked([])} />
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
                        {[
                          { key: 'name', label: 'Empresa', sort: 'name' as SortKey, mobile: true },
                          ...columns,
                        ].map((column) => (
                          <th
                            scope="col"
                            key={column.key}
                            aria-sort={
                              query.order_by === column.sort
                                ? query.direction === 'desc'
                                  ? 'descending'
                                  : 'ascending'
                                : 'none'
                            }
                            className={
                              'p-2 sm:p-4' +
                              (column.key === 'name' ? '' : ' num') +
                              (column.mobile ? '' : ' hidden sm:table-cell')
                            }
                          >
                            <span className="flex items-center gap-1">
                              <button
                                className="flex items-center gap-1 whitespace-nowrap"
                                onClick={() => sort(column.sort)}
                              >
                                {column.label}
                                {query.order_by === column.sort &&
                                  (query.direction === 'desc' ? (
                                    <ArrowDown size={12} aria-hidden="true" />
                                  ) : (
                                    <ArrowUp size={12} aria-hidden="true" />
                                  ))}
                              </button>
                              {column.key !== 'name' && (
                                <Term
                                  k={('term' in column && column.term) || column.key}
                                  name={column.label}
                                />
                              )}
                            </span>
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
                            <span className="inline-flex items-center gap-2">
                              <FollowButton symbol={row.symbol} compact />
                              <label className="flex items-center gap-2">
                                <input
                                  type="checkbox"
                                  className="size-4 accent-primary"
                                  aria-label={'Comparar ' + row.symbol}
                                  checked={picked.includes(row.symbol)}
                                  disabled={
                                    !picked.includes(row.symbol) && picked.length >= MAX_COMPARED
                                  }
                                  onChange={() => toggle(row.symbol)}
                                />
                                {row.rank}
                              </label>
                            </span>
                          </td>
                          <th scope="row" className="max-w-72 p-2 font-normal sm:p-4">
                            <Link
                              to={
                                '/empresas/' +
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
                            <SummaryText summary={row.summary} className="mt-1" />
                            <BlockBars summary={row.summary} compact />
                            <details className="mt-2 text-xs sm:hidden">
                              <summary className="cursor-pointer text-primary">
                                Más métricas de {row.symbol}
                              </summary>
                              <dl className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 text-foreground">
                                {columns
                                  .filter((column) => !column.mobile)
                                  .map((column) => (
                                    <div key={column.key} className="contents">
                                      <dt>
                                        <Term k={column.term ?? column.key}>{column.label}</Term>
                                      </dt>
                                      <dd className="text-right">{column.value(row)}</dd>
                                    </div>
                                  ))}
                              </dl>
                            </details>
                          </th>
                          {columns.map((column) => (
                            <RankCell
                              key={column.key}
                              className={
                                'num whitespace-nowrap ' +
                                (column.mobile
                                  ? 'p-2 font-semibold sm:p-4'
                                  : 'hidden p-4 sm:table-cell')
                              }
                              position={column.position?.(row)}
                              scope={column.scope ?? ''}
                            >
                              {column.value(row)}
                            </RankCell>
                          ))}
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
                  {evidence.data && (
                    <UnevenEvidenceNote evidence={evidence.data} className="pb-3" />
                  )}
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
