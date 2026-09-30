import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { getComparison } from '@/shared/api/client';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Button } from '@/shared/ui/button';
import { metric } from '@/shared/lib/format';
import { useRanking } from './queries';
import { Evidence } from './evidence';

const fields = [
  ['composite_score', 'Composite Score'],
  ['score_coverage', 'Cobertura'],
  ['confidence', 'Confianza'],
  ['price', 'Precio'],
  ['market_cap', 'Capitalización'],
  ['pe', 'PER'],
  ['pb', 'Precio / valor contable'],
  ['roe', 'ROE'],
  ['operating_margin', 'Margen operativo'],
  ['revenue_growth', 'Crecimiento ingresos'],
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
      <header>
        <Link className="text-sm text-primary" to="/mercado">
          ← Mercado
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Comparar empresas</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Elige entre dos y cinco empresas. Todas las métricas y unidades proceden del mismo ranking
          que el Screener.
        </p>
      </header>
      <section aria-label="Selección de empresas" className="rounded-xl border bg-card p-5">
        {universe.isPending && <LoadingState />}
        {universe.isError && (
          <ErrorState error={universe.error} retry={() => void universe.refetch()} />
        )}
        {universe.data && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: Math.min(5, Math.max(2, symbols.length + 1)) }, (_, slot) => (
              <label key={slot} className="text-xs font-medium">
                Empresa {slot + 1}
                <select
                  aria-label={'Empresa ' + (slot + 1)}
                  value={symbols[slot] ?? ''}
                  onChange={(event) => choose(slot, event.target.value)}
                  className="mt-1.5 h-10 w-full rounded-md border bg-background px-2 text-sm"
                >
                  <option value="">Seleccionar</option>
                  {options.map((row) => (
                    <option key={row.symbol} value={row.symbol}>
                      {row.symbol} · {row.name}
                    </option>
                  ))}
                </select>
              </label>
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
          <section className="overflow-x-auto rounded-xl border bg-card p-5">
            <h2 className="mb-4 text-xl font-semibold">Métricas comparables</h2>
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
                    <th className="py-3 font-medium">{label}</th>
                    {comparison.data?.items.map((item) => (
                      <td key={item.symbol} className="py-3 tabular-nums">
                        {metric(item.metrics[key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <Button asChild variant="outline">
            <Link to="/mercado">Volver al Screener</Link>
          </Button>
        </>
      )}
    </div>
  );
}
