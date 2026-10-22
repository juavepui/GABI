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
  return (
    <section
      aria-label="Cobertura del universo por bloque"
      className="mb-5 flex flex-wrap items-end justify-between gap-3 rounded-xl border bg-card p-4"
    >
      <div className="min-w-0 flex-1 text-sm">
        {warnings.length > 0 ? (
          <div
            role="status"
            className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
          >
            <p className="font-medium">
              <Term k="block_coverage">Cobertura del universo por bloque</Term> degradada: el
              ranking incluye bloques con menos del {Math.round(threshold * 100)} % del universo con
              todas sus métricas.
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
              <Term k="block_coverage">Cobertura del universo por bloque</Term>: en todos los
              bloques del score, al menos el {Math.round(threshold * 100)} % del universo (
              {coverage.data.universe} empresas) tiene todas sus métricas.
            </p>
          )
        )}
      </div>
      <CoverageThreshold value={threshold} onChange={setThreshold} />
    </section>
  );
}
