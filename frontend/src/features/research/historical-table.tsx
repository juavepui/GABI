import { useState, type CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getHistoricalTable } from '@/shared/api/client';
import type { HistoricalColumn } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

const PAGE = 100;
const SECTOR_ES: Record<string, string> = {
  'Information Technology': 'Tecnología de la información',
  'Health Care': 'Salud',
  Financials: 'Financiero',
  'Consumer Discretionary': 'Consumo discrecional',
  'Communication Services': 'Servicios de comunicación',
  Industrials: 'Industria',
  'Consumer Staples': 'Consumo básico',
  Energy: 'Energía',
  Utilities: 'Utilities (servicios públicos)',
  'Real Estate': 'Inmobiliario',
  Materials: 'Materiales',
};

const fixed = (value: number, digits: number) =>
  new Intl.NumberFormat('es-ES', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);

function format(column: HistoricalColumn, value: number | string | null | undefined): string {
  if (value == null) return '—';
  if (typeof value === 'string')
    return column.key === 'sector' ? (SECTOR_ES[value] ?? value) : value;
  if (column.key === 'market_cap') return fixed(value / 1e9, 1) + ' mil M$';
  if (column.unit === 'fraction') return fixed(value * 100, 1) + ' %';
  if (column.unit === 'count') return fixed(value, 0);
  if (column.unit === 'USD') return fixed(value, 2) + ' $';
  return fixed(value, 2);
}

/** Same red → amber → green scale as the old table (percentile 0-100, 100 = best in its sector). */
function background(pct: number | null | undefined): CSSProperties | undefined {
  if (pct == null) return undefined;
  const clamped = Math.max(0, Math.min(100, pct));
  const hue = clamped <= 50 ? (clamped / 50) * 40 : 40 + ((clamped - 50) / 50) * 102;
  return { backgroundColor: `hsl(${Math.round(hue)}, 65%, 40%)`, color: 'white' };
}

export function HistoricalTable({ jobId }: { jobId: string }) {
  const [hideNoData, setHideNoData] = useState(true);
  const [sort, setSort] = useState<string | null>(null);
  const [descending, setDescending] = useState(true);
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: ['research', 'historical-table', jobId, hideNoData, sort, descending, offset],
    queryFn: ({ signal }) =>
      getHistoricalTable(jobId, { hideNoData, sort, descending, offset, limit: PAGE }, signal),
    placeholderData: (previous) => previous,
  });

  function sortBy(key: string) {
    if (sort === key) setDescending(!descending);
    else {
      setSort(key);
      setDescending(true);
    }
    setOffset(0);
  }

  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data!;
  const last = Math.min(offset + PAGE, data.total);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={hideNoData}
            onChange={(event) => {
              setHideNoData(event.target.checked);
              setOffset(0);
            }}
          />
          Ocultar empresas sin ningún dato reconstruido
        </label>
        <span className="text-muted-foreground">
          {data.total === 0 ? 'Sin filas' : `${offset + 1}–${last} de ${data.total}`}
          {sort ? ` · ordenado por ${data.columns.find((c) => c.key === sort)?.label ?? sort}` : ''}
        </span>
      </div>
      <div className="max-h-[560px] overflow-auto rounded-lg border">
        <table className="w-max min-w-full text-left text-xs" aria-label="Métricas reconstruidas">
          <thead className="sticky top-0 bg-card">
            <tr className="border-b text-muted-foreground">
              <th className="sticky left-0 bg-card px-2 py-2">Empresa</th>
              {data.columns.map((column) => (
                <th
                  key={column.key}
                  className="px-2"
                  aria-sort={
                    sort === column.key ? (descending ? 'descending' : 'ascending') : undefined
                  }
                >
                  <button
                    type="button"
                    className="whitespace-nowrap underline-offset-2 hover:underline"
                    onClick={() => sortBy(column.key)}
                  >
                    {column.label}
                    {sort === column.key ? (descending ? ' ↓' : ' ↑') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.symbol} className="border-b last:border-0">
                <th scope="row" className="sticky left-0 bg-card px-2 py-1.5 font-medium">
                  {row.symbol}
                </th>
                {data.columns.map((column) => (
                  <td
                    key={column.key}
                    className="whitespace-nowrap px-2"
                    style={column.colored ? background(row.colors[column.key]) : undefined}
                  >
                    {format(column, row.values[column.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
        >
          Anteriores
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={last >= data.total}
          onClick={() => setOffset(offset + PAGE)}
        >
          Siguientes
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Verde mejor · ámbar medio · rojo peor, comparado con el resto de empresas de su sector
        (aproximado salvo que exista una foto point-in-time anterior; sin sector conocido, contra
        todo el universo). Las columnas sin color no se usan para puntuar. Dilución, rentabilidad de
        recompra y CAPEX/flujo operativo se muestran en % y adquisiciones en dólares: la tabla
        antigua los imprimía sin convertir.
      </p>
    </div>
  );
}
