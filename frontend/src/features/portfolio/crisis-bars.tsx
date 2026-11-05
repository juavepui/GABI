import type { ReactNode } from 'react';
import type { Reading } from '@/shared/api/generated/types.gen';
import { formatMoney } from '@/shared/lib/format';
import { ChartFrame } from '@/shared/ui/charts/chart-frame';
import { CompareBars } from '@/shared/ui/charts/compare-bars';

type Scenario = { id: string; label: string; change_eur: number; exceeds_tolerance: boolean };

// Always with the thousands point («3.500 €»), as the backend sentence writes it.
const eur = (value: number) => formatMoney(value, { currency: 'EUR', digits: 0, grouping: true });

/**
 * «¿Aguantaría tu dinero una crisis?» (#325): euros lost in each declared shock against what the investor
 * accepts to lose. The sentence and the tolerance in euros come from the backend; a shock that would gain
 * money is drawn as no loss and said in words.
 */
export function CrisisBars({
  rows,
  reading,
  note,
  table,
}: {
  rows: Scenario[];
  reading: Reading | null | undefined;
  note: ReactNode;
  table: ReactNode;
}) {
  if (!rows.length) return null;
  const tolerance = Number(reading?.values.tolerance_eur ?? NaN);
  return (
    <ChartFrame
      className="mt-5"
      title="¿Aguantaría tu dinero una crisis?"
      conclusion={reading?.text}
      note={note}
      table={table}
    >
      <CompareBars
        label="Euros que perderías en cada crisis"
        rows={rows.map((row) => ({
          label: row.label,
          value: -row.change_eur,
          flag: row.exceeds_tolerance ? 'Más de lo que aceptas perder: revisa tu plan' : null,
        }))}
        format={(value) => (value >= 0 ? '−' + eur(value) : '+' + eur(-value))}
        valueLabel="Lo que perderías"
        limit={
          Number.isFinite(tolerance)
            ? { value: tolerance, label: 'Lo que aceptas perder' }
            : undefined
        }
      />
    </ChartFrame>
  );
}
