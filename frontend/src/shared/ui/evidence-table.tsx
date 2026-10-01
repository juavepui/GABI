import type { EvidenceRow } from '@/shared/api/generated/types.gen';

const pct = (value: number | null | undefined, digits = 0) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value * 100) + ' %';
const points = (value: number | null | undefined) =>
  value == null ? '—' : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 }).format(value);

/** Top-20 evidence of the ranking: categories from published rules, never a probability of gains. */
export function EvidenceTable({
  rows,
  onSelect,
}: {
  rows: EvidenceRow[];
  onSelect?: (symbol: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-xs" aria-label="Evidencia del ranking">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="py-2">Empresa</th>
            <th>Score</th>
            <th>Cobertura ponderada</th>
            <th>Confianza de evidencia</th>
            <th>Persistencia Top-20</th>
            <th>Score con apoyo tras Holm</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.symbol} className="border-b last:border-0">
              <td className="py-1.5">
                {onSelect ? (
                  <button
                    type="button"
                    className="text-primary underline"
                    onClick={() => onSelect(row.symbol)}
                  >
                    {row.symbol}
                  </button>
                ) : (
                  row.symbol
                )}
              </td>
              <td>{points(row.score)}</td>
              <td>{points(row.weighted_data_coverage)}</td>
              <td>{row.confidence_level}</td>
              <td>{row.top20_persistence == null ? 'No estimable' : pct(row.top20_persistence)}</td>
              <td>
                {row.validated_score_fraction == null
                  ? 'No atribuible'
                  : pct(row.validated_score_fraction, 1)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
