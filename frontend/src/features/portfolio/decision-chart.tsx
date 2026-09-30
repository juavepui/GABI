import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip } from 'recharts';
import type { DecisionProgress } from '@/shared/api/generated/types.gen';

export default function DecisionChart({ curve }: { curve: DecisionProgress['curve'] }) {
  return (
    <div role="img" aria-label="Evolución del plan y SPY en base 100" className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={curve}>
          <XAxis dataKey="date" minTickGap={36} tick={{ fontSize: 10 }} />
          <YAxis width={72} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="portfolio"
            stroke="#22764f"
            dot={false}
            connectNulls={false}
            name="Cartera"
          />
          <Line
            type="monotone"
            dataKey="spy"
            stroke="#d09028"
            dot={false}
            connectNulls={false}
            name="SPY"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
