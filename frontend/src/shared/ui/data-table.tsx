import type { ReactNode } from 'react';

/**
 * Scroll container for long tables: the header row stays visible while scrolling, numeric cells
 * marked with `num` align right. Styles live in theme.css (`.data-table`).
 */
export function DataTable({
  label,
  children,
  className = '',
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className={'data-table max-h-[75vh] overflow-auto ' + className}
    >
      {children}
    </div>
  );
}
