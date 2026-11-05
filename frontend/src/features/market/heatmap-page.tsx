import { lazy, Suspense, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getHeatmap } from '@/shared/api/client';
import type { HeatmapCompany, HeatmapResponse } from '@/shared/api/generated/types.gen';
import { formatNumber } from '@/shared/lib/format';
import { Button } from '@/shared/ui/button';
import { HowToRead } from '@/shared/ui/how-to-read';
import { PageHeader } from '@/shared/ui/page-header';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { BAND } from './heatmap-colors';

const HeatmapChart = lazy(() => import('./heatmap-chart'));

/** One row per sector, best mean score first: the same data as the map, readable without colour. */
function SectorList({ data }: { data: HeatmapResponse }) {
  return (
    <div className="space-y-3">
      {data.sectors.map((sector) => {
        const members = data.companies
          .filter((item) => item.sector === sector.sector)
          .sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9));
        return (
          <details key={sector.sector} className="rounded-xl border bg-card p-4">
            <summary className="cursor-pointer text-sm">
              <span className="font-semibold">{sector.sector}</span>
              <span className="text-muted-foreground">
                {' '}
                · {sector.companies} {sector.companies === 1 ? 'empresa' : 'empresas'} · puntuación
                media{' '}
                {sector.mean_score == null
                  ? 'sin dato'
                  : formatNumber(sector.mean_score, { digits: 1 })}{' '}
                · {sector.in_top} entre las mejores
              </span>
            </summary>
            <ul className="mt-3 divide-y text-sm">
              {members.map((item) => (
                <CompanyLine key={item.symbol} item={item} />
              ))}
            </ul>
          </details>
        );
      })}
    </div>
  );
}

function CompanyLine({ item }: { item: HeatmapCompany }) {
  return (
    <li className="flex items-center gap-3 py-1.5">
      <span
        aria-hidden="true"
        className="size-3 shrink-0 rounded-sm border"
        style={{ background: BAND[item.band].fill }}
      />
      <Link
        className="w-16 shrink-0 font-semibold text-primary"
        to={'/empresas/' + encodeURIComponent(item.symbol)}
      >
        {item.symbol}
      </Link>
      <span className="min-w-0 flex-1 truncate text-muted-foreground">{item.name}</span>
      <span className="text-right text-xs tabular-nums">
        {item.composite_score == null ? (
          <span title={item.reason ?? undefined}>Sin puntuación</span>
        ) : (
          <>
            {formatNumber(item.composite_score, { digits: 1 })} · puesto {item.rank}
          </>
        )}
      </span>
    </li>
  );
}

/** «Mapa del mercado» (#311): every company by sector, sized by its value in the stock market, coloured by score. */
export function HeatmapPage() {
  const [view, setView] = useState<'map' | 'list'>('map');
  const query = useQuery({
    queryKey: ['market', 'heatmap'],
    queryFn: ({ signal }) => getHeatmap(signal),
  });
  const data = query.data;
  const unplaced = data?.companies.filter((item) => item.market_cap == null) ?? [];
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Descubrir"
        title="Mapa del mercado"
        description={
          <>
            Todas las empresas del S&amp;P 500 de un vistazo: agrupadas por sector, cada cuadro del
            tamaño de la empresa en bolsa y del color de su puntuación GABI. Sirve para ver dónde
            están las mejor puntuadas; no es una recomendación.
          </>
        }
      />
      {query.isPending && <LoadingState />}
      {query.isError && <ErrorState error={query.error} retry={() => void query.refetch()} />}
      {data && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <ul aria-label="Leyenda de colores" className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {data.bands.map((band, index) => (
                <li key={band.band} className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="size-3 rounded-sm border"
                    style={{ background: BAND[band.band].fill }}
                  />
                  {band.min_score == null
                    ? `menos de ${formatNumber(data.bands[index - 1]?.min_score ?? 30, { digits: 0 })}`
                    : index === 0
                      ? `${formatNumber(band.min_score, { digits: 0 })} o más`
                      : `${formatNumber(band.min_score, { digits: 0 })}–${formatNumber(data.bands[index - 1].min_score, { digits: 0 })}`}
                </li>
              ))}
              <li className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="size-3 rounded-sm border border-dashed border-[#52514e]"
                  style={{ background: BAND.none.fill }}
                />
                sin puntuación
              </li>
            </ul>
            <div className="flex gap-1" role="group" aria-label="Forma de verlo">
              <Button
                size="sm"
                variant={view === 'map' ? 'secondary' : 'ghost'}
                aria-pressed={view === 'map'}
                onClick={() => setView('map')}
              >
                Mapa
              </Button>
              <Button
                size="sm"
                variant={view === 'list' ? 'secondary' : 'ghost'}
                aria-pressed={view === 'list'}
                onClick={() => setView('list')}
              >
                Lista por sectores
              </Button>
            </div>
          </div>
          {view === 'map' ? (
            <>
              <div className="hidden sm:block">
                <Suspense
                  fallback={
                    <p role="status" className="p-12 text-sm text-muted-foreground">
                      Preparando el mapa…
                    </p>
                  }
                >
                  <HeatmapChart data={data} />
                </Suspense>
              </div>
              <div className="sm:hidden">
                <p className="mb-3 text-xs text-muted-foreground">
                  En una pantalla pequeña el mapa no se lee bien; aquí tienes lo mismo en lista.
                </p>
                <SectorList data={data} />
              </div>
            </>
          ) : (
            <SectorList data={data} />
          )}
          <p className="text-xs text-muted-foreground">
            {data.scored} de {data.companies.length} empresas tienen puntuación.
            {unplaced.length > 0 &&
              (unplaced.length === 1
                ? ' 1 no aparece en el mapa porque no está guardado su valor en bolsa: '
                : ` ${unplaced.length} no aparecen en el mapa porque no está guardado su valor en bolsa: `) +
                unplaced.map((item) => item.symbol).join(', ') +
                (unplaced.length === 1 ? ' (está en la lista).' : ' (están en la lista).')}
          </p>
          <HowToRead>
            El tamaño de cada cuadro es lo que vale la empresa en bolsa (su capitalización): las
            gigantes ocupan mucho y las pequeñas poco. El color es su puntuación GABI de hoy, la
            misma del Ranking ({data.model_id}): azul cuanto más alta, gris en la zona media y
            naranja cuanto más baja; en gris claro con borde discontinuo, las que no tienen
            puntuación por falta de datos. Cada cuadro lleva también su número, y la lista por
            sectores dice lo mismo sin colores. «Entre las mejores» es el 20 % de empresas con más
            puntuación. Que un sector tenga muchas empresas bien puntuadas no dice que vaya a subir.
          </HowToRead>
        </>
      )}
    </div>
  );
}
