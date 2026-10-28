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
import type { ComparisonPricesResponse } from '@/shared/api/generated/types.gen';
import { dateLabel, formatNumber } from '@/shared/lib/format';

// Distinct hues for up to five companies; SPY stays grey and dashed as the reference.
const COLORS = ['#2563eb', '#16a34a', '#d97706', '#9333ea', '#db2777'];
const BENCHMARK_COLOR = '#6b7280';

/** Adjusted closes rebased to 100 by the backend; this only draws them. */
export default function ComparisonChart({ data }: { data: ComparisonPricesResponse }) {
  if (!data.points.length)
    return (
      <p role="status" className="py-16 text-center text-sm text-muted-foreground">
        No hay una sesión con precio de todas las empresas y del SPY en esta ventana.
      </p>
    );
  const series = [...data.symbols, data.benchmark];
  const rows = data.points.map((point) => ({ date: point.date, ...point.values }));
  const last = data.points[data.points.length - 1];
  return (
    <>
      <div
        className="h-72 w-full"
        role="img"
        aria-label={
          'Precio ajustado en base 100 desde ' +
          dateLabel(data.base_date) +
          ' de ' +
          series.join(', ') +
          '. Valores finales en la lista inferior.'
        }
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={rows} margin={{ top: 12, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="#e4e9e1" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => dateLabel(String(d))}
              minTickGap={60}
              tick={{ fontSize: 11, fill: '#637169' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(v) => String(Math.round(Number(v)))}
              tick={{ fontSize: 11, fill: '#637169' }}
              axisLine={false}
              tickLine={false}
              width={40}
            />
            <Tooltip
              labelFormatter={(label) => dateLabel(String(label))}
              formatter={(v, name) => [
                formatNumber(v == null ? null : Number(v), { digits: 1 }),
                String(name),
              ]}
              contentStyle={{ borderRadius: 10, borderColor: '#dfe5dc', fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {series.map((symbol, index) => (
              <Line
                key={symbol}
                type="linear"
                dataKey={symbol}
                name={symbol}
                stroke={symbol === data.benchmark ? BENCHMARK_COLOR : COLORS[index % COLORS.length]}
                strokeDasharray={symbol === data.benchmark ? '5 4' : undefined}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <ul
        className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs"
        aria-label={'Valor el ' + dateLabel(last.date)}
      >
        {series.map((symbol) => (
          <li key={symbol}>
            {symbol}:{' '}
            <span className="font-medium tabular-nums">
              {formatNumber(last.values[symbol], { digits: 1 })}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
