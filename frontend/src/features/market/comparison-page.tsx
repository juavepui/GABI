import { lazy, Suspense, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { getComparison, getComparisonPrices } from '@/shared/api/client';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Button } from '@/shared/ui/button';
import { CompanyPicker } from '@/shared/ui/company-picker';
import { dateLabel, metric } from '@/shared/lib/format';
import type { CompanyRow, ComparisonResponse, Metric } from '@/shared/api/generated/types.gen';
import { useRanking } from './queries';
import { Evidence } from './evidence';
import { RankCell, RankLegend, RankValue } from '@/shared/ui/rank-cell';
import { PageHeader } from '@/shared/ui/page-header';
import { sourceLabel } from './provenance';
import { ComparisonChecklist } from './comparison-checklist';
import {
  drawdownDates,
  drawdownOf,
  drawdownValue,
  historySpan,
  useRiskWindows,
} from './risk-windows';

const ComparisonChart = lazy(() => import('./comparison-chart'));

const sections: { title: string; fields: [string, string][] }[] = [
  {
    title: 'Score y bloques',
    fields: [
      ['composite_score', 'Composite Score'],
      ['value_score', 'Bloque valor'],
      ['quality_score', 'Bloque calidad'],
      ['momentum_score', 'Bloque momentum'],
      ['risk_score', 'Bloque riesgo'],
      ['score_coverage', 'Métricas disponibles'],
      ['confidence', 'Cobertura ponderada'],
    ],
  },
  {
    title: 'Valoración',
    fields: [
      ['price', 'Precio'],
      ['market_cap', 'Capitalización'],
      ['pe', 'PER'],
      ['ev_ebitda', 'EV/EBITDA'],
      ['pb', 'Precio / valor contable'],
      ['dividend_yield', 'Rentabilidad por dividendo'],
    ],
  },
  {
    title: 'Calidad y salud',
    fields: [
      ['roe', 'ROE'],
      ['roic', 'ROIC'],
      ['operating_margin', 'Margen operativo'],
      ['revenue_growth_yoy', 'Crecimiento ingresos'],
      ['debt_to_equity', 'Deuda / patrimonio'],
    ],
  },
  {
    title: 'Riesgo',
    fields: [
      ['volatility', 'Volatilidad'],
      ['max_drawdown', 'Caída máxima (todo el histórico)'],
      ['beta_calc', 'Beta frente al SPY'],
    ],
  },
];

const WINDOWS: [number, string][] = [
  [126, '6 meses'],
  [252, '1 año'],
  [756, '3 años'],
];

/** Capitalization in the same compact words as Ranking and the company page. */
const show = (key: string, value: Metric | undefined) => metric(value, key === 'market_cap');

function earnings(item: CompanyRow): string {
  const next = item.next_earnings;
  if (!next) return '—';
  const when = next.days_until === 0 ? 'hoy' : `en ${next.days_until} días`;
  return `${dateLabel(next.event_date)} (${when}${next.is_estimate ? ', estimado' : ''})`;
}

function FieldSource({ data, field }: { data: ComparisonResponse; field: string }) {
  const source = data.metric_sources[field];
  return source ? (
    <span className="block text-xs font-normal text-muted-foreground">{sourceLabel(source)}</span>
  ) : null;
}

function SectionRow({ title, span }: { title: string; span: number }) {
  return (
    <tr className="border-b bg-muted/40">
      <th
        scope="colgroup"
        colSpan={span}
        className="px-2 py-2 text-xs font-semibold uppercase text-muted-foreground"
      >
        {title}
      </th>
    </tr>
  );
}

function PriceSection({ symbols }: { symbols: string[] }) {
  const [bars, setBars] = useState(252);
  const prices = useQuery({
    queryKey: ['market', 'comparison', 'prices', symbols, bars],
    queryFn: ({ signal }) => getComparisonPrices(symbols, bars, signal),
  });
  return (
    <section className="rounded-xl border bg-card p-5" aria-labelledby="comparison-prices">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="comparison-prices" className="text-xl font-semibold">
          Evolución del precio
        </h2>
        <div role="group" aria-label="Ventana del gráfico" className="flex gap-1">
          {WINDOWS.map(([value, label]) => (
            <Button
              key={value}
              size="sm"
              variant={bars === value ? 'default' : 'outline'}
              aria-pressed={bars === value}
              onClick={() => setBars(value)}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Cierre ajustado de la caché local (Yahoo) en base 100 desde la primera sesión en la que
        todas las empresas y el SPY tienen precio
        {prices.data?.base_date ? ` (${dateLabel(prices.data.base_date)})` : ''}. Es rentabilidad
        pasada y no anticipa la futura.
      </p>
      {prices.isPending && <LoadingState />}
      {prices.isError && <ErrorState error={prices.error} retry={() => void prices.refetch()} />}
      {prices.data && (
        <Suspense fallback={<LoadingState />}>
          <ComparisonChart data={prices.data} />
        </Suspense>
      )}
    </section>
  );
}

export function ComparisonPage() {
  const [params, setParams] = useSearchParams();
  const symbols = params.getAll('symbols').slice(0, 5);
  const universe = useRanking({ limit: 500, hide_no_data: false });
  const comparison = useQuery({
    queryKey: ['market', 'comparison', symbols],
    queryFn: ({ signal }) => getComparison(symbols, signal),
    enabled: symbols.length >= 2 && symbols.length <= 5,
  });
  const options = universe.data?.items ?? [];
  function choose(slot: number, value: string) {
    const next = [...symbols];
    if (value) next[slot] = value;
    else next.splice(slot, 1);
    const clean = next.filter((symbol, index) => symbol && next.indexOf(symbol) === index);
    const updated = new URLSearchParams();
    clean.forEach((symbol) => updated.append('symbols', symbol));
    setParams(updated);
  }
  const compared = comparison.data?.items.map((item) => item.symbol) ?? [];
  const windows = useRiskWindows(compared);
  const risk = (symbol: string) => windows.data?.items.find((item) => item.symbol === symbol);
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/descubrir', label: 'Ranking' }}
        title="Comparar empresas"
        description={
          <>
            Busca entre dos y cinco empresas por símbolo o nombre, o márcalas en el Ranking. Las
            métricas proceden del mismo ranking que el Screener y el checklist es el de cada ficha.
          </>
        }
      />
      <section aria-label="Selección de empresas" className="rounded-xl border bg-card p-5">
        {universe.isPending && <LoadingState />}
        {universe.isError && (
          <ErrorState error={universe.error} retry={() => void universe.refetch()} />
        )}
        {universe.data && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: Math.min(5, Math.max(2, symbols.length + 1)) }, (_, slot) => (
              <CompanyPicker
                key={slot}
                label={'Empresa ' + (slot + 1)}
                options={options}
                value={symbols[slot] ?? ''}
                onChange={(symbol) => choose(slot, symbol)}
              />
            ))}
          </div>
        )}
        {symbols.length < 2 && (
          <p className="mt-4 text-sm text-muted-foreground">
            Selecciona dos empresas para ver la comparación.
          </p>
        )}
      </section>
      {comparison.isPending && symbols.length >= 2 && <LoadingState />}
      {comparison.isError && (
        <ErrorState error={comparison.error} retry={() => void comparison.refetch()} />
      )}
      {comparison.data && (
        <>
          <Evidence model={comparison.data.model} data={comparison.data.data} />
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-4 text-xl font-semibold">Métricas comparables</h2>
            <div className="space-y-3 sm:hidden" aria-label="Comparación por empresa">
              {comparison.data.items.map((item) => (
                <article key={item.symbol} className="rounded-lg border p-3 text-sm">
                  <Link
                    className="font-semibold text-primary"
                    to={'/empresas/' + encodeURIComponent(item.symbol)}
                  >
                    {item.symbol} · {item.name}
                  </Link>
                  <p className="mt-2 flex justify-between gap-2">
                    <span>Composite Score</span>
                    <RankValue
                      position={comparison.data.positions.composite_score?.[item.symbol]}
                      scope="de los comparados"
                    >
                      {metric(item.metrics.composite_score)}
                    </RankValue>
                  </p>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-primary">
                      Todas las métricas de {item.symbol}
                    </summary>
                    {sections.map((section) => (
                      <div key={section.title} className="mt-3">
                        <h3 className="text-xs font-semibold uppercase text-muted-foreground">
                          {section.title}
                        </h3>
                        <dl className="mt-1 space-y-2">
                          {section.fields
                            .filter(([key]) => key !== 'composite_score')
                            .map(([key, label]) => (
                              <div className="flex justify-between gap-3" key={key}>
                                <dt>{label}</dt>
                                <dd className="text-right">
                                  <RankValue
                                    position={comparison.data.positions[key]?.[item.symbol]}
                                    scope="de los comparados"
                                  >
                                    {show(key, item.metrics[key])}
                                  </RankValue>
                                </dd>
                              </div>
                            ))}
                        </dl>
                      </div>
                    ))}
                    <p className="mt-3 flex justify-between gap-3">
                      <span>Próximos resultados</span>
                      <span className="text-right">{earnings(item)}</span>
                    </p>
                  </details>
                </article>
              ))}
            </div>
            <div className="hidden overflow-x-auto sm:block">
              <table className="w-full min-w-[600px] text-left text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="pb-3">Métrica</th>
                    {comparison.data.items.map((item) => (
                      <th className="pb-3" key={item.symbol}>
                        <Link
                          className="text-primary"
                          to={'/empresas/' + encodeURIComponent(item.symbol)}
                        >
                          {item.symbol}
                        </Link>
                        <span className="mt-1 block text-xs font-normal text-muted-foreground">
                          {item.name}
                          {item.sector ? ' · ' + item.sector : ''}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                {sections.map((section) => (
                  <tbody key={section.title}>
                    <SectionRow title={section.title} span={comparison.data.items.length + 1} />
                    {section.fields.map(([key, label]) => (
                      <tr key={key} className="border-b last:border-0">
                        <th scope="row" className="py-3 pr-3 font-medium">
                          {label}
                          <FieldSource data={comparison.data} field={key} />
                        </th>
                        {comparison.data.items.map((item) => (
                          <RankCell
                            key={item.symbol}
                            className="px-3 py-3"
                            position={comparison.data.positions[key]?.[item.symbol]}
                            scope="de los comparados"
                          >
                            {show(key, item.metrics[key])}
                            {(key === 'max_drawdown' || key === 'volatility') && (
                              <span className="block text-xs text-muted-foreground">
                                {key === 'max_drawdown'
                                  ? drawdownDates(drawdownOf(risk(item.symbol), 'full'))
                                  : historySpan(risk(item.symbol))}
                              </span>
                            )}
                          </RankCell>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                ))}
                <tbody>
                  {(['5y', '3y'] as const).map((window) => (
                    <tr key={window} className="border-b">
                      <th scope="row" className="py-3 pr-3 font-medium">
                        Caída máxima · {window === '5y' ? '5 años' : '3 años'}
                        <span className="block text-xs font-normal text-muted-foreground">
                          GABI con precios en caché · informativa, no puntúa
                        </span>
                      </th>
                      {comparison.data.items.map((item) => {
                        const row = drawdownOf(risk(item.symbol), window);
                        return (
                          <td key={item.symbol} className="px-3 py-3 tabular-nums">
                            {windows.isPending ? '…' : drawdownValue(row)}
                            <span className="block text-xs text-muted-foreground">
                              {drawdownDates(row)}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
                <tbody>
                  <SectionRow title="Catalizadores" span={comparison.data.items.length + 1} />
                  <tr>
                    <th scope="row" className="py-3 pr-3 font-medium">
                      Próximos resultados
                      <span className="block text-xs font-normal text-muted-foreground">
                        Yahoo Finance
                      </span>
                    </th>
                    {comparison.data.items.map((item) => (
                      <td key={item.symbol} className="px-3 py-3">
                        {earnings(item)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <RankLegend>
              Rojo peor, verde mejor entre las empresas comparadas, según si la métrica es mejor
              alta o baja en el score (un PER bajo o una volatilidad baja son mejores). Precio y
              capitalización no tienen mejor ni peor y quedan sin color. Un asterisco (*) indica que
              el histórico en caché es más corto que la ventana.
            </RankLegend>
          </section>
          <section className="rounded-xl border bg-card p-5" aria-labelledby="comparison-checklist">
            <h2 id="comparison-checklist" className="mb-4 text-xl font-semibold">
              Checklist y múltiplos frente a su historia y su sector
            </h2>
            <ComparisonChecklist symbols={compared} />
          </section>
          <PriceSection symbols={compared} />
          <Button asChild variant="outline">
            <Link to="/descubrir">Volver al Screener</Link>
          </Button>
        </>
      )}
    </div>
  );
}
