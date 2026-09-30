import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip } from 'recharts';
import type { CurvePoint } from '@/shared/api/generated/types.gen';

export default function SimulationChart({ curve }: { curve: CurvePoint[] }) {
  return (
    <div role="img" aria-label="Evolución del valor simulado" className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={curve}>
          <XAxis dataKey="date" minTickGap={36} tick={{ fontSize: 10 }} />
          <YAxis width={72} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#22764f"
            dot={false}
            connectNulls={false}
            name="Valor"
          />
          <Line type="monotone" dataKey="cash" stroke="#d09028" dot={false} name="Efectivo" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
