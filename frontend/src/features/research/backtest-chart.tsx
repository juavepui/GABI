import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import type { BacktestCurvePoint } from '@/shared/api/generated/types.gen';

export default function BacktestChart({
  curve,
  withUniverse,
}: {
  curve: BacktestCurvePoint[];
  withUniverse: boolean;
}) {
  return (
    <div role="img" aria-label="Curva de capital del backtest" className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={curve}>
          <XAxis dataKey="fecha" minTickGap={36} tick={{ fontSize: 10 }} />
          <YAxis width={80} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="estrategia"
            name="Estrategia"
            stroke="var(--chart-1)"
            dot={false}
          />
          {withUniverse && (
            <Line
              type="monotone"
              dataKey="universo_ew"
              name="Universo equiponderado"
              stroke="var(--chart-3)"
              dot={false}
            />
          )}
          <Line type="monotone" dataKey="spy" name="SPY" stroke="var(--chart-2)" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
