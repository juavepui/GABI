import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRankingCoverage } from '@/shared/api/client';
import { CoverageThreshold, WarningText } from '@/shared/ui/coverage';
import { Term } from '@/shared/ui/term';

/** Score blocks whose complete coverage falls below the threshold, over the whole ranking. */
export function CoverageWarnings() {
  const [threshold, setThreshold] = useState(0.7);
  const coverage = useQuery({
    queryKey: ['market', 'coverage', threshold],
    queryFn: ({ signal }) => getRankingCoverage(threshold, signal),
    placeholderData: (previous) => previous,
  });
  const warnings = coverage.data?.warnings ?? [];
  const threshold_pct = Math.round(threshold * 100);
  return (
    <section
      aria-label="Datos que faltan por apartado"
      className="mb-5 rounded-xl border bg-card p-4 text-sm"
    >
      {warnings.length > 0 ? (
        <div
          role="status"
          className="rounded-lg border border-warning-border bg-warning-soft p-3 text-warning-ink"
        >
          <p className="font-medium">
            Ojo: en algún apartado de la puntuación faltan muchos datos (
            <Term k="block_coverage">cobertura por apartado</Term>)
          </p>
          <p className="mt-1">
            Menos del {threshold_pct} % de las empresas tienen todos los datos de estos apartados,
            así que esa parte de la puntuación es menos fiable:
          </p>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((warning) => (
              <li key={warning}>
                <WarningText text={warning} />
              </li>
            ))}
          </ul>
        </div>
      ) : (
        coverage.data && (
          <p className="text-muted-foreground">
            Datos completos: en cada apartado de la puntuación, al menos el {threshold_pct} % de las{' '}
            {coverage.data.universe} empresas tienen todos sus datos (
            <Term k="block_coverage">cobertura por apartado</Term>).
          </p>
        )
      )}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          Cambiar el mínimo exigido
        </summary>
        <div className="mt-2">
          <CoverageThreshold value={threshold} onChange={setThreshold} />
        </div>
      </details>
    </section>
  );
}
