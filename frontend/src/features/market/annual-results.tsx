import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getCompanyAnnualResults } from '@/shared/api/client';
import type { AnnualResultsPoint } from '@/shared/api/generated/types.gen';
import { dateText, formatCompactMoney, formatNumber } from '@/shared/lib/format';
import { ChartFrame } from '@/shared/ui/charts/chart-frame';
import { YearColumns } from '@/shared/ui/charts/year-columns';
import { Term } from '@/shared/ui/term';

type Figure = 'revenue' | 'net_income' | 'free_cash_flow';

/** «391 mil M» / «758 M»: short enough to sit on a column; the table gives the full amount. */
function short(value: number): string {
  const size = Math.abs(value);
  if (size >= 1e9) return formatNumber(value / 1e9, { digits: size >= 1e11 ? 0 : 1 }) + ' mil M';
  if (size >= 1e6) return formatNumber(value / 1e6, { digits: 0 }) + ' M';
  return formatNumber(value, { digits: 0 });
}

const PANELS: { key: Figure; title: ReactNode; name: string }[] = [
  { key: 'revenue', title: 'Ingresos', name: 'Ingresos por ejercicio' },
  { key: 'net_income', title: 'Beneficio neto', name: 'Beneficio neto por ejercicio' },
  {
    key: 'free_cash_flow',
    title: <Term k="free_cashflow">Caja libre</Term>,
    name: 'Caja libre por ejercicio',
  },
];

/** Years without a figure, grouped by the backend's reason, so every gap says why. */
function gaps(points: AnnualResultsPoint[], key: Figure): string[] {
  const reasons = new Map<string, string[]>();
  for (const point of points) {
    const reason = point.missing[key];
    if (reason) reasons.set(reason, [...(reasons.get(reason) ?? []), point.label]);
  }
  return [...reasons].map(([reason, years]) => `Sin dato en ${years.join(', ')}: ${reason}`);
}

/** «¿El negocio crece?» (#328): revenue, net income and free cash flow by fiscal year, from the SEC reports. */
export function AnnualResults({ symbol }: { symbol: string }) {
  const query = useQuery({
    queryKey: ['market', 'annual-results', symbol],
    queryFn: ({ signal }) => getCompanyAnnualResults(symbol, signal),
  });
  const data = query.data;
  if (!data) return null;
  const points = data.points;
  const marked = points.some((point) => point.restated);
  return (
    <section
      aria-label="Ingresos y beneficio por año"
      className="mb-6 rounded-xl border bg-card p-5"
    >
      <ChartFrame
        title="¿El negocio crece?"
        conclusion={data.reading.text}
        note={
          points.length > 0 && (
            <>
              Cifras de sus informes anuales a la SEC (10-K), en dólares; «M» son millones. Cada año
              es su ejercicio fiscal, que puede no acabar en diciembre.
              {marked &&
                ' Los años con * la empresa los rehízo después: se ven tal como se publicaron.'}{' '}
              Son resultados pasados: no dicen cómo le irá en el futuro.
            </>
          )
        }
        table={
          points.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b text-muted-foreground">
                  <tr>
                    <th className="pb-1.5">Ejercicio</th>
                    <th className="pb-1.5 text-right">Ingresos</th>
                    <th className="pb-1.5 text-right">Beneficio neto</th>
                    <th className="pb-1.5 text-right">Caja libre</th>
                    <th className="pb-1.5 text-right">Publicado el</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {points.map((point) => (
                    <tr key={point.fiscal_year_end} className="border-b last:border-0">
                      <td className="py-1">
                        {point.label}
                        {point.restated ? ' *' : ''}
                      </td>
                      {PANELS.map(({ key }) => (
                        <td key={key} className="py-1 text-right">
                          {point[key] == null ? 'Sin dato' : formatCompactMoney(point[key])}
                        </td>
                      ))}
                      <td className="py-1 text-right">
                        {point.filed ? dateText(point.filed) : 'Sin fecha'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted-foreground">Sin ejercicios que mostrar.</p>
          )
        }
      >
        {points.length > 0 && (
          <div className="grid gap-5 md:grid-cols-3">
            {PANELS.map(({ key, title, name }) => (
              <div key={key} className="min-w-0 space-y-2">
                <p className="text-sm font-medium">{title}</p>
                <YearColumns
                  label={name}
                  format={short}
                  columns={points.map((point) => ({
                    label: point.label,
                    value: point[key] ?? null,
                    marked: point.restated,
                  }))}
                />
                {gaps(points, key).map((text) => (
                  <p key={text} className="text-xs text-muted-foreground">
                    {text}
                  </p>
                ))}
              </div>
            ))}
          </div>
        )}
      </ChartFrame>
    </section>
  );
}
