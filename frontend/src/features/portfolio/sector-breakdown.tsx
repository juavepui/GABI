import type { PlanResponse } from '@/shared/api/generated/types.gen';
import { Folded } from '@/shared/ui/folded';
import { formatNumber } from '@/shared/lib/format';

const pct = (value: number | null | undefined) =>
  value == null ? '—' : formatNumber(value, { digits: 1 }) + ' %';
const points = (value: number | null | undefined) =>
  value == null ? '—' : (value > 0 ? '+' : '') + formatNumber(value, { digits: 1 });

/** Sector and industry weights of the target, computed by the backend; descriptive, not a selection rule. */
export function SectorBreakdown({ data }: { data: PlanResponse }) {
  return (
    <section aria-label="Reparto por sector" className="rounded-xl border bg-card p-5">
      <h2 className="text-xl font-semibold">Reparto por sector</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Peso de cada sector en la cartera objetivo frente a su peso en el S&amp;P 500. Es
        descriptivo: la selección congelada no limita sectores. {data.index_weight_basis}
      </p>
      {data.concentration.length > 0 ? (
        <div
          role="status"
          className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <p className="font-medium">Concentración por encima del umbral</p>
          <ul className="mt-1 list-disc pl-5">
            {data.concentration.map((warning) => (
              <li key={warning.kind + warning.name}>
                {warning.kind === 'sector' ? 'Sector' : 'Industria'} {warning.name}:{' '}
                {pct(warning.weight_percent)} con {warning.positions}{' '}
                {warning.positions === 1 ? 'posición' : 'posiciones'} (umbral{' '}
                {pct(warning.limit_percent)}).
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-4 text-sm">
          Ningún sector supera el {pct(data.sector_limit_percent)} ni ninguna industria el{' '}
          {pct(data.industry_limit_percent)}.
        </p>
      )}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs sm:text-sm">
          <caption className="sr-only">Peso por sector frente al S&amp;P 500</caption>
          <thead className="border-b text-xs text-muted-foreground">
            <tr>
              <th className="pb-2">Sector</th>
              <th className="pb-2 text-right">Posiciones</th>
              <th className="pb-2 text-right">Cartera</th>
              <th className="pb-2 text-right">S&amp;P 500</th>
              <th className="pb-2 text-right">Diferencia (pp)</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {data.sectors.map((row) => (
              <tr key={row.sector} className="border-b last:border-0">
                <td className="py-2">{row.sector}</td>
                <td className="text-right">{row.positions}</td>
                <td className="text-right">{pct(row.weight_percent)}</td>
                <td className="text-right">{pct(row.index_weight_percent)}</td>
                <td className="text-right">{points(row.difference_points)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.industries.length > 0 && (
        <div className="mt-4">
          <Folded title="Peso por industria" className="rounded-lg border p-3 text-sm">
            <ul className="divide-y text-sm">
              {data.industries.map((row) => (
                <li key={row.industry} className="flex justify-between gap-4 py-2">
                  <span>
                    {row.industry}
                    <span className="ml-2 text-xs text-muted-foreground">{row.sector}</span>
                  </span>
                  <span className="tabular-nums">
                    {pct(row.weight_percent)} · {row.positions}
                  </span>
                </li>
              ))}
            </ul>
          </Folded>
        </div>
      )}
    </section>
  );
}
