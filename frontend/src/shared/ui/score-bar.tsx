import { cn } from '@/shared/lib/utils';

/**
 * A 0–100 score as a thin bar next to its number (#320), to scan a list without reading figures. The bar is
 * decoration: the number beside it is what screen readers read. Neutral colour, so it never competes with the
 * colour that already says the level (RankCell).
 */
export function ScoreBar({
  value,
  className = '',
}: {
  value: number | null | undefined;
  className?: string;
}) {
  if (value == null || !Number.isFinite(value)) return null;
  const width = Math.min(Math.max(value, 0), 100);
  return (
    <span
      aria-hidden="true"
      data-score-bar={Math.round(width)}
      className={cn(
        'inline-block h-1.5 w-12 shrink-0 overflow-hidden rounded-full bg-muted align-middle',
        className,
      )}
    >
      <span className="block h-full rounded-full bg-primary/70" style={{ width: `${width}%` }} />
    </span>
  );
}
