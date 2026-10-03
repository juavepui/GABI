import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { getComparison } from '@/shared/api/client';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Button } from '@/shared/ui/button';
import { CompanyPicker } from '@/shared/ui/company-picker';
import { metric } from '@/shared/lib/format';
import { useRanking } from './queries';
import { Evidence } from './evidence';
import { RankCell, RankLegend, RankValue } from '@/shared/ui/rank-cell';
import { PageHeader } from '@/shared/ui/page-header';

const fields = [
  ['composite_score', 'Composite Score'],
  ['score_coverage', 'Cobertura'],
  ['confidence', 'Cobertura ponderada'],
  ['price', 'Precio'],
  ['market_cap', 'Capitalización'],
  ['pe', 'PER'],
  ['pb', 'Precio / valor contable'],
  ['roe', 'ROE'],
  ['operating_margin', 'Margen operativo'],
  ['revenue_growth_yoy', 'Crecimiento ingresos'],
  ['volatility', 'Volatilidad'],
  ['max_drawdown', 'Caída máxima'],
] as const;

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
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/mercado', label: 'Mercado' }}
        title="Comparar empresas"
        description={
          <>
            Busca entre dos y cinco empresas por símbolo o nombre. Todas las métricas y unidades
            proceden del mismo ranking que el Screener.
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
                    to={'/mercado/empresas/' + encodeURIComponent(item.symbol)}
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
                    <dl className="mt-3 space-y-2">
                      {fields.slice(1).map(([key, label]) => (
                        <div className="flex justify-between gap-3" key={key}>
                          <dt>{label}</dt>
                          <dd className="text-right">
                            <RankValue
                              position={comparison.data.positions[key]?.[item.symbol]}
                              scope="de los comparados"
                            >
                              {metric(item.metrics[key])}
                            </RankValue>
                          </dd>
                        </div>
                      ))}
                    </dl>
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
                          to={'/mercado/empresas/' + encodeURIComponent(item.symbol)}
                        >
                          {item.symbol}
                        </Link>
                        <span className="mt-1 block text-xs font-normal text-muted-foreground">
                          {item.name}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {fields.map(([key, label]) => (
                    <tr key={key} className="border-b last:border-0">
                      <th className="py-3 pr-3 font-medium">{label}</th>
                      {comparison.data?.items.map((item) => (
                        <RankCell
                          key={item.symbol}
                          className="px-3 py-3"
                          position={comparison.data?.positions[key]?.[item.symbol]}
                          scope="de los comparados"
                        >
                          {metric(item.metrics[key])}
                        </RankCell>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <RankLegend>
              Rojo peor, verde mejor entre las empresas comparadas, según si la métrica es mejor
              alta o baja en el score (un PER bajo o una volatilidad baja son mejores). Precio y
              capitalización no tienen mejor ni peor y quedan sin color.
            </RankLegend>
          </section>
          <Button asChild variant="outline">
            <Link to="/mercado">Volver al Screener</Link>
          </Button>
        </>
      )}
    </div>
  );
}
