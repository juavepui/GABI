import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { hiddenDrawdown } from './learn-content';

export default function HiddenDrawdownChart() {
  return (
    <div
      className="h-56 w-full"
      role="img"
      aria-label="Ejemplo sintético: un trimestre empieza en 100, cae un 28 % a mitad y termina en 104"
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart data={hiddenDrawdown()} margin={{ top: 12, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#e4e9e1" strokeDasharray="3 3" />
          <XAxis dataKey="day" tick={{ fontSize: 11 }} minTickGap={40} />
          <YAxis domain={[60, 110]} width={40} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value) => Number(value).toFixed(1)}
            labelFormatter={(d) => `Sesión ${d}`}
          />
          <Line dataKey="value" name="Capital (ejemplo sintético)" dot={false} stroke="#2563eb" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
