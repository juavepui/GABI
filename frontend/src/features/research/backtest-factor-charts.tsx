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
  strategy: '#22764f',
  spy: '#4467b3',
  rf: '#8a8a8a',
  universe_ew: '#d09028',
  spy_beta: '#8d4fb3',
  ff6: '#c2413b',
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
            fill="#22764f"
            fillOpacity={0.15}
          />
          <Line dataKey="estimate" name="Coeficiente" stroke="#22764f" dot />
          {full != null && (
            <ReferenceLine y={full} strokeDasharray="4 4" label="Muestra completa" />
          )}
          <ReferenceLine y={0} stroke="#8a8a8a" />
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
              stroke={COLORS[name] ?? '#555'}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
