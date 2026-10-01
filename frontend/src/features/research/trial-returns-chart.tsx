import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TrialPoint } from '@/shared/api/generated/types.gen';

const percent = (value: number) =>
  new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 }).format(value * 100) + ' %';

/** Published return of each period, as it is in the artifact (no compounding here). */
export default function TrialReturnsChart({ points }: { points: TrialPoint[] }) {
  return (
    <div
      className="h-48 w-full"
      role="img"
      aria-label={`Rentabilidad publicada de ${points.length} periodos`}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#e4e9e1" strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
          <YAxis
            tickFormatter={(value) => percent(Number(value))}
            width={52}
            tick={{ fontSize: 10 }}
          />
          <Tooltip formatter={(value) => percent(Number(value))} />
          <Bar dataKey="value" name="Rentabilidad del periodo">
            {points.map((point) => (
              <Cell key={point.date} fill={(point.value ?? 0) >= 0 ? '#059669' : '#e11d48'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
