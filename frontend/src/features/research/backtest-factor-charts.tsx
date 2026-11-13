import {
  Area,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export type RollingPoint = { end: string; estimate: number; low: number; high: number };
export type WealthPoint = { date: string } & Record<string, number | string | null>;

const COLORS: Record<string, string> = {
  strategy: 'var(--chart-1)',
  spy: 'var(--chart-2)',
  rf: 'var(--chart-6)',
  universe_ew: 'var(--chart-3)',
  spy_beta: 'var(--chart-4)',
  ff6: 'var(--chart-5)',
};

export function RollingChart({ points, full }: { points: RollingPoint[]; full: number | null }) {
  const data = points.map((point) => ({ ...point, band: [point.low, point.high] }));
  return (
    <div role="img" aria-label="Coeficiente en ventanas móviles" className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data}>
          <XAxis dataKey="end" minTickGap={30} tick={{ fontSize: 10 }} />
          <YAxis width={70} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
          <Tooltip />
          <Area
            dataKey="band"
            name="IC 95 % puntual HAC"
            stroke="none"
            fill="var(--chart-1)"
            fillOpacity={0.15}
          />
          <Line dataKey="estimate" name="Coeficiente" stroke="var(--chart-1)" dot />
          {full != null && (
            <ReferenceLine y={full} strokeDasharray="4 4" label="Muestra completa" />
          )}
          <ReferenceLine y={0} stroke="var(--chart-6)" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function WealthChart({
  points,
  series,
  labels,
}: {
  points: WealthPoint[];
  series: string[];
  labels: Record<string, string>;
}) {
  return (
    <div role="img" aria-label="Curvas comparables del benchmark" className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <XAxis dataKey="date" minTickGap={30} tick={{ fontSize: 10 }} />
          <YAxis width={60} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
          <Tooltip />
          <Legend />
          {series.map((name) => (
            <Line
              key={name}
              dataKey={name}
              name={labels[name] ?? name}
              stroke={COLORS[name] ?? 'var(--chart-6)'}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
