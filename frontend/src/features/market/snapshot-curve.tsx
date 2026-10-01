import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SnapshotCurvePoint } from '@/shared/api/generated/types.gen';
import { dateLabel } from '@/shared/lib/format';

export default function SnapshotCurve({ points }: { points: SnapshotCurvePoint[] }) {
  return (
    <div
      className="h-64 w-full"
      role="img"
      aria-label={`Valor de la cesta guardada y del SPY, base 100 en la fecha guardada, ${points.length} sesiones`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart data={points} margin={{ top: 12, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#e4e9e1" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tickFormatter={(d) => dateLabel(String(d))}
            minTickGap={60}
            tick={{ fontSize: 11 }}
          />
          <YAxis domain={['auto', 'auto']} width={48} tick={{ fontSize: 11 }} />
          <Tooltip labelFormatter={(label) => dateLabel(String(label))} />
          <Legend />
          <Line dataKey="basket" name="Cesta guardada" dot={false} stroke="#2563eb" />
          <Line dataKey="spy" name="SPY" dot={false} stroke="#dc2626" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
