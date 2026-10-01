import type { TailSeries } from '@/shared/api/generated/types.gen';

const pct = (value: number | null | undefined, digits = 2) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value * 100) + ' %';
const num = (value: number | null | undefined, digits = 3) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value);

function tailWarnings(row: TailSeries): string[] {
  const summary = row.summary;
  if (!summary) return [];
  return (
    [
      ['95', summary.level_95],
      ['99', summary.level_99],
    ] as const
  ).flatMap(([level, tail]) =>
    tail.status === 'empty'
      ? [`${row.name}: no hay retornos para estimar la cola al ${level} %.`]
      : tail.status === 'below_resolution'
        ? [
            `${row.name} · ${level} %: masa de cola ${num(tail.tail_mass, 2)} < 1 observación. VaR y ES coinciden con la peor pérdida observada; el extremo no está resuelto por la muestra.`,
          ]
        : tail.status === 'sparse'
          ? [
              `${row.name} · ${level} %: cola escasa (${num(tail.tail_mass, 2)} observaciones equivalentes). El resultado depende de muy pocos retornos.`,
            ]
          : [],
  );
}

export function TailRiskTable({
  horizon,
  series,
  message,
}: {
  horizon: string;
  series: TailSeries[];
  message: string | null | undefined;
}) {
  return (
    <>
      <p className="mt-2 text-xs text-muted-foreground">
        Horizonte: {horizon}. Estimaciones históricas sin anualizar; pérdidas positivas, ganancias
        negativas.
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Cartera</th>
              <th>n</th>
              <th>VaR 95 %</th>
              <th>ES/CVaR 95 %</th>
              <th>VaR 99 %</th>
              <th>ES/CVaR 99 %</th>
              <th>Asimetría</th>
              <th>Exceso de curtosis</th>
              <th>Masa de cola 95 %</th>
              <th>Masa de cola 99 %</th>
            </tr>
          </thead>
          <tbody>
            {series.map((row) =>
              row.summary ? (
                <tr key={row.name} className="border-b last:border-0">
                  <td className="py-2">{row.name}</td>
                  <td>{row.summary.n_obs}</td>
                  <td>{pct(row.summary.level_95.var)}</td>
                  <td>{pct(row.summary.level_95.expected_shortfall)}</td>
                  <td>{pct(row.summary.level_99.var)}</td>
                  <td>{pct(row.summary.level_99.expected_shortfall)}</td>
                  <td>{num(row.summary.skewness)}</td>
                  <td>{num(row.summary.excess_kurtosis)}</td>
                  <td>{num(row.summary.level_95.tail_mass, 2)}</td>
                  <td>{num(row.summary.level_99.tail_mass, 2)}</td>
                </tr>
              ) : (
                <tr key={row.name} className="border-b last:border-0">
                  <td className="py-2">{row.name}</td>
                  <td colSpan={9} className="text-destructive">
                    No disponible: {row.error}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-400">
        {series.flatMap(tailWarnings).map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        VaR es el umbral de pérdidas; ES/CVaR promedia la peor masa del 5 % o 1 %, ponderando la
        frontera. Asimetría negativa indica cola izquierda; exceso de curtosis normal = 0. La masa
        de cola no cuenta eventos independientes. Estas cifras describen la muestra y no limitan las
        pérdidas futuras. {message}
      </p>
    </>
  );
}
