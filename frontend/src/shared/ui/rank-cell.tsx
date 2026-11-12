import type { ReactNode } from 'react';

/** Background for a ranked cell: 0 = worst (red) .. 1 = best (green); the position comes from the backend. */
function rankStyle(position: number | null | undefined) {
  if (position == null) return undefined;
  // Hue from the position; saturation and lightness from the theme (#321), so it reads in dark mode.
  return {
    backgroundColor: `hsl(${Math.round(position * 120)}, var(--rank-saturation), var(--rank-lightness))`,
  };
}

function rankTitle(position: number | null | undefined, scope: string) {
  if (position === 1) return 'El mejor ' + scope;
  if (position === 0) return 'El peor ' + scope;
  return undefined;
}

/** A table cell coloured by its position; the best one is bold. */
export function RankCell({
  position,
  scope,
  className = '',
  children,
}: {
  position: number | null | undefined;
  scope: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <td
      className={
        'tabular-nums text-foreground ' + (position === 1 ? 'font-semibold ' : '') + className
      }
      style={rankStyle(position)}
      title={rankTitle(position, scope)}
    >
      {children}
    </td>
  );
}

/** Same backend position as RankCell, for compact mobile records. */
export function RankValue({
  position,
  scope,
  children,
}: {
  position: number | null | undefined;
  scope: string;
  children: ReactNode;
}) {
  return (
    <span
      className="rounded px-1.5 py-0.5 tabular-nums text-foreground"
      style={rankStyle(position)}
      title={rankTitle(position, scope)}
    >
      {children}
    </span>
  );
}

export function RankLegend({ children }: { children: ReactNode }) {
  return (
    <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
      <span
        className="mr-2 inline-block h-3 w-24 rounded-full align-middle"
        style={{
          background:
            'linear-gradient(to right, hsl(0, var(--rank-saturation), var(--rank-legend-lightness)), hsl(60, var(--rank-saturation), var(--rank-legend-lightness)), hsl(120, var(--rank-saturation), var(--rank-legend-lightness)))',
        }}
        aria-hidden="true"
      />
      {children}
    </p>
  );
}
