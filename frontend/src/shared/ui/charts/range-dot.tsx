import type { CSSProperties } from 'react';

export type RangeMark = { value: number; label: string };

/**
 * A value as a dot on its range (#323): the line goes from `min` to `max`, short ticks mark the references
 * (a median, the sector) with their name under them, and the dot is today's value with «Hoy» above it. All
 * positions come from values the backend sent; the scale only places them. Colours are theme variables, and
 * the same reading is given in words through `description`, so the dot is never the only way to read it.
 */
export function RangeDot({
  min,
  max,
  value,
  marks = [],
  format,
  description,
  lowLabel = 'más barata',
  highLabel = 'más cara',
}: {
  min: number;
  max: number;
  value: number;
  marks?: RangeMark[];
  format: (value: number) => string;
  description: string;
  lowLabel?: string;
  highLabel?: string;
}) {
  const low = Math.min(min, value, ...marks.map((mark) => mark.value));
  const high = Math.max(max, value, ...marks.map((mark) => mark.value));
  const span = high - low || 1;
  const share = (point: number) => (point - low) / span;
  const at = (point: number) => `${share(point) * 100}%`;
  // A label near an edge grows inwards, so it is never cut off.
  const label = (point: number): CSSProperties => ({
    left: at(point),
    transform:
      share(point) < 0.12
        ? 'translateX(0)'
        : share(point) > 0.88
          ? 'translateX(-100%)'
          : 'translateX(-50%)',
  });
  return (
    <div role="img" aria-label={description} className="w-full">
      <div className="relative mx-2 h-5 text-xs" aria-hidden="true">
        <span className="absolute whitespace-nowrap font-semibold" style={label(value)}>
          Hoy {format(value)}
        </span>
      </div>
      <div className="relative mx-2 h-5">
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-muted-foreground/30"
          style={{ left: at(min), width: `calc(${at(max)} - ${at(min)})` }}
        />
        {marks.map((mark) => (
          <div
            key={mark.label}
            className="absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-foreground/70"
            style={{ left: at(mark.value) }}
          />
        ))}
        <div
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-primary"
          style={{ left: at(value) }}
        />
      </div>
      <div
        className="relative mx-2 h-9 text-xs leading-tight text-muted-foreground"
        aria-hidden="true"
      >
        {marks.map((mark, index) => (
          <span
            key={mark.label}
            className="absolute whitespace-nowrap"
            style={{ ...label(mark.value), top: index % 2 ? '1.1rem' : 0 }}
          >
            {mark.label} {format(mark.value)}
          </span>
        ))}
      </div>
      {/* The ends of its own range, under where the line really starts and stops. */}
      <div className="relative mx-2 h-5 text-xs text-muted-foreground" aria-hidden="true">
        <span
          className="absolute whitespace-nowrap"
          style={{ ...label(min), transform: 'translateX(0)' }}
        >
          ← {lowLabel} · {format(min)}
        </span>
        <span
          className="absolute whitespace-nowrap"
          style={{ ...label(max), transform: 'translateX(-100%)' }}
        >
          {format(max)} · {highLabel} →
        </span>
      </div>
    </div>
  );
}
