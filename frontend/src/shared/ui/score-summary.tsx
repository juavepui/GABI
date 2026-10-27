import type { CandidateSummary } from '@/shared/api/generated/types.gen';
import { formatNumber } from '@/shared/lib/format';

const BLOCKS = [
  ['value', 'Valoración'],
  ['quality', 'Calidad'],
  ['momentum', 'Momentum'],
  ['risk', 'Riesgo'],
] as const;

/** «Por qué está aquí» (#184): the backend's sentence, descriptive and never a recommendation. */
export function SummaryText({
  summary,
  className = '',
}: {
  summary: CandidateSummary;
  className?: string;
}) {
  return <span className={'block text-xs text-muted-foreground ' + className}>{summary.text}</span>;
}

/** The four score blocks as bars of 0 to 100 points (100 = best of the universe). `compact` is the
 *  table version: thin bars whose values are read by screen readers and shown on hover. */
export function BlockBars({
  summary,
  compact = false,
}: {
  summary: CandidateSummary;
  compact?: boolean;
}) {
  const blocks = BLOCKS.map(([key, label]) => ({ key, label, value: summary.blocks[key] ?? null }));
  const text = (value: number | null) =>
    value == null ? 'sin dato' : formatNumber(value, { digits: 0 });
  // Green for the strong blocks the sentence names, red for its weak one.
  const fill = (key: (typeof BLOCKS)[number][0]) =>
    'block h-full rounded-full ' +
    (summary.strengths.includes(key)
      ? 'bg-emerald-600'
      : summary.weakness === key
        ? 'bg-red-600'
        : 'bg-primary/70');
  if (compact)
    return (
      <span
        className="mt-1 flex gap-1"
        title={blocks.map((block) => `${block.label} ${text(block.value)}`).join(' · ')}
      >
        <span className="sr-only">
          Bloques del score:{' '}
          {blocks.map((block) => `${block.label} ${text(block.value)}`).join(', ')}
        </span>
        {blocks.map((block) => (
          <span
            key={block.key}
            aria-hidden="true"
            className="h-1.5 w-6 overflow-hidden rounded-full bg-muted"
          >
            <span className={fill(block.key)} style={{ width: `${block.value ?? 0}%` }} />
          </span>
        ))}
      </span>
    );
  return (
    <dl
      className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4"
      aria-label="Bloques del score"
    >
      {blocks.map((block) => (
        <div key={block.key}>
          <dt className="text-muted-foreground">{block.label}</dt>
          <dd className="mt-1 flex items-center gap-2">
            <span
              aria-hidden="true"
              className="block h-2 w-20 overflow-hidden rounded-full bg-muted"
            >
              <span className={fill(block.key)} style={{ width: `${block.value ?? 0}%` }} />
            </span>
            <span className="w-8 text-right font-medium tabular-nums">{text(block.value)}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
