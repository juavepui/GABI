/**
 * A small line without axes next to a number (#323, #327): the shape of its recent history. No range band:
 * with a dozen monthly points it would make normal values look extreme. An optional dashed line marks a
 * reference (a median). The reading in words comes from the backend and is the accessible text, so the line
 * is never the only way to read it. Colours are theme variables.
 */
export function Sparkline({
  values,
  description,
  reference,
  width = 120,
  height = 32,
  className = '',
}: {
  values: number[];
  description: string;
  reference?: number | null;
  width?: number;
  height?: number;
  className?: string;
}) {
  if (values.length < 2) return null;
  const all = reference == null ? values : [...values, reference];
  const low = Math.min(...all);
  const high = Math.max(...all);
  const span = high - low || 1;
  const pad = 2;
  const x = (index: number) => pad + (index / (values.length - 1)) * (width - pad * 2);
  const y = (value: number) => pad + (1 - (value - low) / span) * (height - pad * 2);
  const path = values
    // SVG coordinates, not text: rounded to a tenth with Math.round.
    .map((value, index) => `${Math.round(x(index) * 10) / 10},${Math.round(y(value) * 10) / 10}`)
    .join(' ');
  const last = values[values.length - 1];
  return (
    <svg
      role="img"
      aria-label={description}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      // Stretches to its box (w-full) without thickening the line.
      preserveAspectRatio="none"
      className={'shrink-0 overflow-visible ' + className}
    >
      {reference != null && (
        <line
          x1={pad}
          x2={width - pad}
          y1={y(reference)}
          y2={y(reference)}
          stroke="var(--chart-axis)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
      )}
      <polyline
        points={path}
        fill="none"
        stroke="var(--chart-1)"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={x(values.length - 1)} cy={y(last)} r={2.5} fill="var(--chart-1)" />
    </svg>
  );
}
