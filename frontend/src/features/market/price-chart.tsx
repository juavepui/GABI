import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import type { PricePoint } from '@/shared/api/generated/types.gen';
import { dateLabel, metric } from '@/shared/lib/format';

export default function PriceChart({ prices }: { prices: PricePoint[] }) {
  if (!prices.length)
    return (
      <p role="status" className="py-16 text-center text-sm text-muted-foreground">
        Sin precios disponibles en esta ventana.
      </p>
    );
  return (
    <>
      <div
        className="h-72 w-full"
        role="img"
        aria-label={
          'Histórico de cierre ajustado en USD, ' +
          prices.length +
          ' sesiones. Datos accesibles en la tabla inferior.'
        }
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart
            data={prices}
            margin={{ top: 12, right: 12, bottom: 0, left: 0 }}
            accessibilityLayer
          >
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
              width={48}
            />
            <Tooltip
              labelFormatter={(label) => dateLabel(String(label))}
              formatter={(v) => [
                metric({ value: v == null ? null : Number(v), unit: 'USD' }),
                'Cierre ajustado',
              ]}
              contentStyle={{ borderRadius: 10, borderColor: '#dfe5dc', fontSize: 12 }}
            />
            <Line
              type="linear"
              dataKey="adj_close"
              stroke="#2d654b"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-3 text-xs text-muted-foreground">
        <summary className="cursor-pointer py-2">
          Ver datos del gráfico ({prices.length} sesiones)
        </summary>
        <div className="mt-2 max-h-64 overflow-auto" tabIndex={0} aria-label="Precios por sesión">
          <table className="w-full text-left">
            <caption className="sr-only">
              Serie de precios en USD, sin sustituir ausencias de cierre ajustado.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="p-2">
                  Fecha
                </th>
                <th scope="col" className="p-2">
                  Cierre · USD
                </th>
                <th scope="col" className="p-2">
                  Cierre ajustado · USD
                </th>
              </tr>
            </thead>
            <tbody>
              {prices.map((p) => (
                <tr key={p.date} className="border-t">
                  <th scope="row" className="p-2 font-normal">
                    {dateLabel(p.date)}
                  </th>
                  <td className="p-2">{metric({ value: p.close, unit: 'USD' })}</td>
                  <td className="p-2">{metric({ value: p.adj_close, unit: 'USD' })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}
