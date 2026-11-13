import { TriangleAlert } from 'lucide-react';

export type CompareRow = {
  label: string;
  value: number;
  /** A second bar under the first one, e.g. the same sector in the S&P 500. */
  reference?: number | null;
  /** Shown with an icon and in words, never as colour alone. */
  flag?: string | null;
};

/**
 * Horizontal bars with direct labels (#323): each row's value and, optionally, a paired reference bar and a
 * vertical limit line. The rows, their order and the flags come from the backend; this only draws them.
 * Colours are theme variables; every number is written next to its bar.
 */
export function CompareBars({
  rows,
  format,
  valueLabel,
  referenceLabel,
  limit,
  label,
}: {
  rows: CompareRow[];
  format: (value: number) => string;
  valueLabel: string;
  referenceLabel?: string;
  limit?: { value: number; label: string };
  label: string;
}) {
  const scale = Math.max(
    ...rows.map((row) => Math.max(row.value, row.reference ?? 0)),
    limit?.value ?? 0,
    0.0001,
  );
  const width = (value: number) => `${Math.max((value / scale) * 100, 0)}%`;
  const paired = rows.some((row) => row.reference != null);
  const limitLine = limit && (
    <span
      aria-hidden="true"
      className="absolute -inset-y-0.5 border-l-2 border-dashed border-foreground"
      style={{ left: width(limit.value) }}
    />
  );
  return (
    <div className="space-y-3">
      {(paired || limit) && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Leyenda">
          <li className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded-sm"
              style={{ background: 'var(--chart-1)' }}
            />
            {valueLabel}
          </li>
          {paired && referenceLabel && (
            <li className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="size-3 rounded-sm"
                style={{ background: 'var(--chart-6)' }}
              />
              {referenceLabel}
            </li>
          )}
          {limit && (
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="h-3 border-l-2 border-dashed border-foreground" />
              {limit.label}
            </li>
          )}
        </ul>
      )}
      <ul className="space-y-2.5" aria-label={label}>
        {rows.map((row) => (
          <li
            key={row.label}
            className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-x-3 text-xs sm:grid-cols-[minmax(0,13rem)_1fr]"
          >
            <span className="truncate" title={row.label}>
              {row.label}
            </span>
            <div className="space-y-1">
              <div>
                <div className="flex items-center gap-2">
                  <div className="relative h-3 flex-1">
                    <div
                      className="h-3 rounded-r"
                      style={{ width: width(row.value), background: 'var(--chart-1)' }}
                    />
                    {limitLine}
                  </div>
                  <span className="w-14 shrink-0 text-right tabular-nums">
                    <span className="sr-only">{valueLabel}: </span>
                    {format(row.value)}
                  </span>
                </div>
                {row.reference != null && (
                  <div className="mt-0.5 flex items-center gap-2 text-muted-foreground">
                    <div className="relative h-2 flex-1">
                      <div
                        className="h-2 rounded-r"
                        style={{ width: width(row.reference), background: 'var(--chart-6)' }}
                      />
                      {limitLine}
                    </div>
                    <span className="w-14 shrink-0 text-right tabular-nums">
                      <span className="sr-only">{referenceLabel}: </span>
                      {format(row.reference)}
                    </span>
                  </div>
                )}
              </div>
              {row.flag && (
                <p className="flex items-center gap-1 text-warning-ink">
                  <TriangleAlert size={12} aria-hidden="true" />
                  {row.flag}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
