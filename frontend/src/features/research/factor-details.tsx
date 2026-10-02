import { useState } from 'react';
import type { FactorPreview } from '@/shared/api/generated/types.gen';
import { formatPercent } from '@/shared/lib/format';

const percent = (value: number | null | undefined) => formatPercent(value, { digits: 2 });

export function FactorGlossary() {
  return (
    <details className="rounded-xl border bg-card p-5 text-sm">
      <summary className="cursor-pointer font-medium">
        Qué son Rank IC, ICIR y sector-neutral
      </summary>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-muted-foreground">
        <li>
          <strong>Rank IC</strong>: correlación de Spearman entre el score y el retorno futuro real
          de cada empresa en un periodo, de −1 a +1. Cero significa que el score no ordena quién
          sube más.
        </li>
        <li>
          <strong>ICIR</strong>: IC medio dividido entre su desviación típica; mide si el IC es
          consistente periodo a periodo, no solo alto de media.
        </li>
        <li>
          <strong>Sector-neutral</strong>: el retorno de cada empresa se compara con la media de su
          sector antes de calcular el IC, para separar la selección dentro del sector de la moda
          sectorial.
        </li>
        <li>
          <strong>Rotación del quintil</strong>: fracción de empresas nuevas en un quintil respecto
          al rebalanceo anterior; más rotación es más cara de replicar.
        </li>
      </ul>
    </details>
  );
}

export function FactorQuantiles({
  preview,
  neutral,
}: {
  preview: FactorPreview;
  neutral: boolean;
}) {
  const rows = preview.summary.filter((row) => row.sector_neutral === neutral);
  const factors = [...new Set(rows.map((row) => row.factor))].sort();
  const horizons = [...new Set(rows.map((row) => row.horizonte))].sort((a, b) => a - b);
  const [factorChoice, setFactor] = useState<string | null>(null);
  const [horizonChoice, setHorizon] = useState<number | null>(null);
  const factor = factorChoice != null && factors.includes(factorChoice) ? factorChoice : factors[0];
  const horizon =
    horizonChoice != null && horizons.includes(horizonChoice) ? horizonChoice : horizons[0];
  if (factor == null || horizon == null) return null;
  const quantiles = preview.quantile_means
    .filter((row) => row.factor === factor && row.horizonte === horizon)
    .sort((a, b) => a.quantil - b.quantil);

  return (
    <div className="mt-7">
      <h3 className="font-semibold">
        Retorno medio por quintil{neutral ? ' (sector-neutral)' : ''}
      </h3>
      <div className="mt-3 flex flex-wrap gap-4">
        <label className="text-xs font-medium">
          Factor
          <select
            className="mt-1.5 block h-10 rounded-md border bg-background px-2 text-sm"
            value={factor}
            onChange={(event) => setFactor(event.target.value)}
          >
            {factors.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-medium">
          Horizonte
          <select
            className="mt-1.5 block h-10 rounded-md border bg-background px-2 text-sm"
            value={horizon}
            onChange={(event) => setHorizon(Number(event.target.value))}
          >
            {horizons.map((value) => (
              <option key={value} value={value}>
                {value} meses
              </option>
            ))}
          </select>
        </label>
      </div>
      {quantiles.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Sin datos suficientes para esta combinación de factor y horizonte.
        </p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[320px] text-left text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="py-2">Quintil</th>
                <th>Retorno medio</th>
              </tr>
            </thead>
            <tbody>
              {quantiles.map((row) => (
                <tr key={row.quantil} className="border-b last:border-0">
                  <td className="py-2">Q{row.quantil}</td>
                  <td>{percent(neutral ? row.retorno_medio_neutral : row.retorno_medio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        Q1 es el peor score y el último quintil el mejor. Si el score ordena bien, el retorno
        debería crecer hacia los quintiles altos, no necesariamente en línea recta.
      </p>
    </div>
  );
}

export function SkippedPeriods({ skipped }: { skipped: FactorPreview['skipped'] }) {
  if (skipped.length === 0) return null;
  return (
    <details className="mt-4 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        {skipped.length} periodo(s) saltado(s) por falta de cobertura
      </summary>
      <ul className="mt-2 space-y-1 pl-5 text-muted-foreground">
        {skipped.map((row) => (
          <li key={row.fecha}>
            {row.fecha}: {row.motivo}
          </li>
        ))}
      </ul>
    </details>
  );
}
