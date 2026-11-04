import type { HistoricalCoverage } from '@/shared/api/generated/types.gen';
import { WarningText } from '@/shared/ui/coverage';

export function HistoricalCoverageNotes({
  coverage,
  total,
}: {
  coverage: HistoricalCoverage;
  total: number;
}) {
  const layer = coverage.historical_coverage;
  const members = Math.max(layer?.members ?? 1, 1);
  return (
    <div className="space-y-2 text-sm" aria-label="Cobertura de la reconstrucción" role="region">
      {layer && (
        <p className="rounded-lg border border-sky-300 bg-sky-50 p-3 dark:border-sky-800 dark:bg-sky-950">
          <strong>Capa histórica 2010–2015</strong>: identidad SEC acreditada{' '}
          {layer.identity_accredited}/{layer.members} · precio acreditado {layer.accredited_prices}/
          {layer.members} ({Math.round((100 * layer.accredited_prices) / members)} %) · con score{' '}
          {layer.scored}. Solo se usan datos con origen en la SEC, nunca los guardados por símbolo.
          Las exclusiones están sesgadas hacia empresas que salen del índice y de menor tamaño: no
          uses este periodo para afirmar que se bate al S&amp;P 500 sin las correcciones del #33.
          <span className="mt-1 block text-xs text-muted-foreground">
            Excluidas:{' '}
            {Object.entries(layer.excluded)
              .map(([reason, count]) => `${reason.replaceAll('_', ' ')}: ${count}`)
              .join(', ')}
          </span>
        </p>
      )}
      {coverage.identity && coverage.identity.ambiguous > 0 && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-950">
          {coverage.identity.ambiguous}/{total} empresas con identidad ambigua (varios alias en
          conflicto para esta fecha). No se usan sus datos por símbolo para calcular la puntuación.
        </p>
      )}
      {coverage.identity && coverage.identity.unresolved > 0 && (
        <p className="text-xs text-muted-foreground">
          {coverage.identity.unresolved}/{total} empresas sin identidad histórica acreditada todavía
          (migración no completada): siguen usando la caché por ticker de siempre, sin cambios.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        {total} empresas en la tabla · {coverage.with_fundamentals} con datos de sus cuentas de
        entonces · {coverage.with_price} con precio/capitalización de esa fecha ·{' '}
        {coverage.sector_approximate} con sector aproximado (no hay dato de la época) ·{' '}
        {coverage.no_sector} sin ningún sector conocido.
      </p>
      {coverage.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-amber-950">
          <p className="font-medium">
            ⚠️ En algún apartado de la puntuación faltan muchos datos en esta reconstrucción
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {coverage.warnings.map((warning) => (
              <li key={warning}>
                <WarningText text={warning} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
