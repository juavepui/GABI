import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBacktestDiagnostics } from '@/shared/api/client';
import type { TailSeries, TaxDrag } from '@/shared/api/generated/types.gen';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

const pct = (value: number | null | undefined, digits = 2) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value * 100) + ' %';
const num = (value: number | null | undefined, digits = 3) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value);
const eur = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }).format(value) + ' €';

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

function TaxColumn({ label, tax }: { label: string; tax: TaxDrag }) {
  return (
    <div className="rounded-lg border p-3">
      <h5 className="font-medium">{label}</h5>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
        <dt className="text-muted-foreground">Retorno bruto</dt>
        <dd>{pct(tax.pretax_return)}</dd>
        <dt className="text-muted-foreground">Retorno neto con IRPF</dt>
        <dd>{pct(tax.aftertax_return)}</dd>
        <dt className="text-muted-foreground">Impuesto pagado</dt>
        <dd>{eur(tax.total_tax_paid)}</dd>
        <dt className="text-muted-foreground">Plusvalía sin realizar al final</dt>
        <dd>{eur(tax.unrealized_gain_remaining)}</dd>
      </dl>
    </div>
  );
}

export function BacktestDiagnostics({ jobId, v1 }: { jobId: string; v1: boolean }) {
  const [capital, setCapital] = useState(100000);
  const [applied, setApplied] = useState(100000);
  const query = useQuery({
    queryKey: ['research', 'backtest-diagnostics', jobId, applied],
    queryFn: ({ signal }) => getBacktestDiagnostics(jobId, applied, signal),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data!;
  const tail = data.tail;
  return (
    <div className="space-y-3">
      <details className="rounded-lg border p-4 text-sm">
        <summary className="cursor-pointer font-medium">
          Riesgo de cola · {v1 ? 'retornos por rebalanceo' : 'retornos diarios'}
        </summary>
        {tail.horizon == null ? (
          <p className="mt-2 text-muted-foreground">{tail.message}</p>
        ) : (
          <>
            <p className="mt-2 text-xs text-muted-foreground">
              Horizonte: {tail.horizon}. Estimaciones históricas sin anualizar; pérdidas positivas,
              ganancias negativas.
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
                  {tail.series.map((row) =>
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
              {tail.series.flatMap(tailWarnings).map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted-foreground">
              VaR es el umbral de pérdidas; ES/CVaR promedia la peor masa del 5 % o 1 %, ponderando
              la frontera. Asimetría negativa indica cola izquierda; exceso de curtosis normal = 0.
              La masa de cola no cuenta eventos independientes. Estas cifras describen la muestra y
              no limitan las pérdidas futuras. {tail.message}
            </p>
          </>
        )}
      </details>
      {data.tax && (
        <details className="rounded-lg border p-4 text-sm">
          <summary className="cursor-pointer font-medium">
            Drag fiscal español (aproximado, IRPF base del ahorro)
          </summary>
          <p className="mt-2 text-xs text-muted-foreground">
            El retorno del backtest es bruto. Con turnover alto las plusvalías se realizan
            constantemente y se pierde el diferimiento fiscal de comprar y mantener. Simulación
            aparte con coste medio por cartera y tramos 2024 de la base del ahorro.
          </p>
          <form
            className="mt-3 flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setApplied(capital);
            }}
          >
            <label className="text-xs font-medium">
              Capital inicial de la simulación (€)
              <Input
                className="mt-1.5"
                type="number"
                min={1000}
                step={10000}
                value={capital}
                onChange={(event) => setCapital(Number(event.target.value))}
              />
            </label>
            <button className="h-10 rounded-md border px-3 text-sm" type="submit">
              Recalcular
            </button>
          </form>
          {data.tax.error ? (
            <p className="mt-3 text-muted-foreground">
              Simulación fiscal no disponible: {data.tax.error}
            </p>
          ) : (
            data.tax.strategy &&
            data.tax.spy_buy_and_hold && (
              <>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <TaxColumn label="Estrategia" tax={data.tax.strategy} />
                  <TaxColumn label="SPY comprado y mantenido" tax={data.tax.spy_buy_and_hold} />
                </div>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[480px] text-left text-xs">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="py-2">Año</th>
                        <th>Ganancia/pérdida neta compensada</th>
                        <th>Base imponible</th>
                        <th>Impuesto</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.tax.strategy.tax_by_year.map((row) => (
                        <tr key={row.year} className="border-b last:border-0">
                          <td className="py-2">{row.year}</td>
                          <td>{eur(row.realized_net)}</td>
                          <td>{eur(row.taxable)}</td>
                          <td>{eur(row.tax)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )
          )}
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
            {data.tax.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
