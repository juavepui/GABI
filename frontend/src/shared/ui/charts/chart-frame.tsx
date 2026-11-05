import type { ReactNode } from 'react';

/**
 * Common frame of every GABI chart (#323): the question it answers, the conclusion in words first (written by the
 * backend, never computed here), the chart, an optional source note and the same data as a table. `conclusion`
 * and `table` are required by type, so no chart ships without its sentence or its accessible alternative.
 */
export function ChartFrame({
  title,
  conclusion,
  children,
  table,
  note,
  className = '',
}: {
  title: string;
  conclusion: ReactNode;
  children: ReactNode;
  table: ReactNode;
  note?: ReactNode;
  className?: string;
}) {
  return (
    <figure className={'m-0 space-y-3 ' + className}>
      <figcaption className="space-y-1">
        <p className="text-sm font-semibold">{title}</p>
        <p className="text-sm">{conclusion}</p>
      </figcaption>
      {children}
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
      <details className="text-xs">
        <summary className="cursor-pointer font-medium text-primary">Ver como tabla</summary>
        <div className="mt-2">{table}</div>
      </details>
    </figure>
  );
}
