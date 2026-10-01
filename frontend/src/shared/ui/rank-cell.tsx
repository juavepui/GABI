import type { ReactNode } from 'react';

/** Background for a ranked cell: 0 = worst (red) .. 1 = best (green); the position comes from the backend. */
export function rankStyle(position: number | null | undefined) {
  if (position == null) return undefined;
  return { backgroundColor: `hsl(${Math.round(position * 120)}, 70%, 87%)` };
}

export function rankTitle(position: number | null | undefined, scope: string) {
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

export function RankLegend({ children }: { children: ReactNode }) {
  return (
    <p className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span
        className="inline-block h-3 w-24 shrink-0 rounded-full"
        style={{
          background:
            'linear-gradient(to right, hsl(0,70%,80%), hsl(60,70%,80%), hsl(120,70%,80%))',
        }}
        aria-hidden="true"
      />
      {children}
    </p>
  );
}
