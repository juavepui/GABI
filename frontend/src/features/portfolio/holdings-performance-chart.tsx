import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import type { PerformancePoint } from '@/shared/api/generated/types.gen';

/** Unit value (base 1) of the portfolio and of the S&P 500 with the same flows: flows do not move it. */
export default function HoldingsPerformanceChart({
  portfolio,
  benchmark,
}: {
  portfolio: PerformancePoint[];
  benchmark: PerformancePoint[];
}) {
  const spy = new Map(benchmark.map((point) => [point.date, point.nav]));
  const data = portfolio.map((point) => ({
    date: point.date,
    cartera: point.nav,
    sp500: spy.get(point.date) ?? null,
  }));
  return (
    <div
      role="img"
      aria-label="Evolución de 1 euro invertido en tu cartera y en el S&P 500"
      className="h-64 w-full"
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <XAxis dataKey="date" minTickGap={36} tick={{ fontSize: 10 }} />
          <YAxis width={48} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="cartera" name="Tu cartera" stroke="#22764f" dot={false} />
          <Line
            type="monotone"
            dataKey="sp500"
            name="S&P 500"
            stroke="#5b6bd6"
            dot={false}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
