export type YearColumn = {
  label: string;
  value: number | null;
  /** Drawn dashed and marked with «*»: e.g. figures the company redid afterwards. */
  marked?: boolean;
};

const HEIGHT = 96;

/**
 * Vertical columns by year (#328) with a zero line, so losses and negative cash go below it. Every value is
 * written next to its column (never colour alone), a missing year says «Sin dato», and the backend decides
 * which years exist. Colours are theme variables.
 */
export function YearColumns({
  columns,
  format,
  label,
}: {
  columns: YearColumn[];
  format: (value: number) => string;
  label: string;
}) {
  const values = columns.map((column) => column.value ?? 0);
  const top = Math.max(...values, 0);
  const bottom = Math.min(...values, 0);
  const span = top - bottom || 1;
  const zero = (top / span) * HEIGHT;
  return (
    <ul
      aria-label={label}
      className="grid gap-1.5"
      style={{ gridTemplateColumns: `repeat(${Math.max(columns.length, 1)}, minmax(0, 1fr))` }}
    >
      {columns.map((column) => {
        const value = column.value;
        const size = value == null ? 0 : Math.max((Math.abs(value) / span) * HEIGHT, 1);
        const negative = value != null && value < 0;
        return (
          <li key={column.label} className="flex min-w-0 flex-col items-center text-[11px]">
            <span className="sr-only">
              {column.label}: {value == null ? 'sin dato' : format(value)}
              {column.marked ? ' (cifra rehecha después)' : ''}
            </span>
            <div aria-hidden="true" className="relative w-full" style={{ height: HEIGHT + 32 }}>
              <span
                className="absolute inset-x-0 border-t"
                style={{ top: zero + 16, borderColor: 'var(--chart-axis)' }}
              />
              {value == null ? (
                <span
                  className="absolute inset-x-0 text-center text-muted-foreground"
                  style={{ top: Math.max(zero - 2, 0) }}
                >
                  Sin dato
                </span>
              ) : (
                <>
                  <span
                    className={
                      'absolute inset-x-1 ' +
                      (column.marked ? 'border border-dashed opacity-60 ' : '') +
                      (negative ? 'rounded-b' : 'rounded-t')
                    }
                    style={{
                      top: negative ? zero + 16 : zero + 16 - size,
                      height: size,
                      background: negative ? 'var(--danger)' : 'var(--chart-1)',
                      borderColor: 'var(--foreground)',
                    }}
                  />
                  <span
                    className="absolute inset-x-0 truncate text-center tabular-nums"
                    style={negative ? { top: zero + 16 + size + 1 } : { top: zero + 1 - size }}
                  >
                    {format(value)}
                  </span>
                </>
              )}
            </div>
            <span aria-hidden="true" className="truncate text-muted-foreground">
              {column.label}
              {column.marked ? ' *' : ''}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
