import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getBacktestDiagnostics } from '@/shared/api/client';
import type { TaxDrag } from '@/shared/api/generated/types.gen';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { CoverageThreshold, WarningText } from '@/shared/ui/coverage';
import { TailRiskTable } from './tail-risk-table';
import { formatNumber, formatPercent } from '@/shared/lib/format';

const pct = (value: number | null | undefined, digits = 2) => formatPercent(value, { digits });
const eur = (value: number | null | undefined) =>
  value == null ? '—' : formatNumber(value, { digits: 0 }) + ' €';

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
  const [threshold, setThreshold] = useState(0.7);
  const query = useQuery({
    queryKey: ['research', 'backtest-diagnostics', jobId, applied, threshold],
    queryFn: ({ signal }) => getBacktestDiagnostics(jobId, applied, threshold, signal),
    placeholderData: (previous) => previous,
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data!;
  const tail = data.tail;
  return (
    <div className="space-y-3">
      <div
        className="rounded-lg border p-4 text-sm"
        role="region"
        aria-label="Calidad de datos por periodo"
      >
        <p className="text-xs text-muted-foreground">
          Limitaciones estructurales de datos históricos: sector aproximado y cobertura SEC
          incompleta. Se avisa de cada rebalanceo cuya cobertura queda por debajo del umbral.
        </p>
        <div className="mt-2">
          <CoverageThreshold value={threshold} onChange={setThreshold} />
        </div>
        {data.quality_warnings.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">
            Ningún rebalanceo por debajo del umbral.
          </p>
        ) : (
          <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-400">
            {data.quality_warnings.map((row) => (
              <li key={row.fecha}>
                {row.fecha}:{' '}
                {row.messages.map((message, index) => (
                  <span key={index}>
                    {index > 0 && ' · '}
                    <WarningText text={message} />
                  </span>
                ))}
              </li>
            ))}
          </ul>
        )}
      </div>
      <details className="rounded-lg border p-4 text-sm">
        <summary className="cursor-pointer font-medium">
          Riesgo de cola · {v1 ? 'retornos por rebalanceo' : 'retornos diarios'}
        </summary>
        {tail.horizon == null ? (
          <p className="mt-2 text-muted-foreground">{tail.message}</p>
        ) : (
          <TailRiskTable horizon={tail.horizon} series={tail.series} message={tail.message} />
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
