import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPublishedFactors } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatNumber } from '@/shared/lib/format';

const labels: Record<string, string> = {
  pe: 'PER',
  pb: 'P/VC',
  ev_ebitda: 'EV/EBITDA',
  roic: 'ROIC',
  operating_margin: 'Margen operativo',
  revenue_cagr_3y: 'Crecimiento de ingresos',
  fcf_cagr_3y: 'Crecimiento de caja libre',
  momentum_12m: 'Momento 12 meses',
  rel_strength_6m: 'Fuerza relativa 6 meses',
  price_vs_sma200: 'Precio frente a SMA 200',
  debt_to_equity: 'Deuda/patrimonio',
  volatility: 'Volatilidad',
  max_drawdown: 'Caída máxima',
};
const number = (value: number | null, digits = 3) => formatNumber(value, { digits });
const percentage = (value: number | null) => (value == null ? '—' : number(value * 100, 1) + ' %');
const exportBase = '/api/v1/research/published-factors/exports/';

export function PublishedFactorMap() {
  const query = useQuery({
    queryKey: ['research', 'published-factors'],
    queryFn: ({ signal }) => getPublishedFactors(signal),
  });
  const [selected, setSelected] = useState('pe');
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  if (!data) return null;
  const factor = data.factors.find((row) => row.metric === selected) ?? data.factors[0];
  return (
    <section
      className="space-y-5 rounded-xl border bg-card p-5"
      aria-labelledby="published-factors-heading"
    >
      <div>
        <h2 id="published-factors-heading" className="text-xl font-semibold">
          Mapa de evidencia por factor
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {data.factors.length} señales y {data.n_dates} trimestres publicados. Evidencia
          retrospectiva:{' '}
          {data.holm_significant_count === 0
            ? 'ninguna señal supera la corrección Holm al 5 %.'
            : `${data.holm_significant_count} señales superan la corrección Holm al 5 %.`}{' '}
          El diagnóstico por industria SIC no valida una ventaja frente al S&amp;P 500 ni selecciona
          pesos.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[740px] text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Factor</th>
              <th>IC medio</th>
              <th>ICIR</th>
              <th>p Holm</th>
              <th>Clasificación</th>
              <th>Trimestres</th>
              <th>Spread Q5−Q1</th>
            </tr>
          </thead>
          <tbody>
            {data.factors.map((row) => (
              <tr key={row.metric} className="border-b last:border-0">
                <td className="py-2 font-medium">{labels[row.metric] ?? row.metric}</td>
                <td>{number(row.ic_mean)}</td>
                <td>{number(row.icir)}</td>
                <td>{number(row.p_holm)}</td>
                <td>{row.classification}</td>
                <td>{row.n_periods}</td>
                <td>{percentage(row.q_spread)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t pt-5">
        <h3 className="font-semibold">Estabilidad por industria SIC fechada</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          La clasificación SEC era conocida antes de cada señal. SIC y GICS son taxonomías
          distintas. El IC descriptivo exige al menos {data.minimum_pairs} pares por trimestre y{' '}
          {data.minimum_summary_periods} trimestres para el resumen.
        </p>
        <p className="mt-3 text-sm">
          Cobertura industria/empresa-fecha: <strong>{percentage(data.classified_fraction)}</strong>{' '}
          ({data.n_classified.toLocaleString('es-ES')} de {data.n_eligible.toLocaleString('es-ES')}{' '}
          observaciones elegibles).
        </p>
        {factor && (
          <>
            <label className="mt-4 block text-sm font-medium">
              Señal · estabilidad por industria
              <select
                className="mt-1.5 block h-10 w-full max-w-sm rounded-md border bg-background px-2 text-sm"
                value={factor.metric}
                onChange={(event) => setSelected(event.target.value)}
              >
                {data.factors.map((row) => (
                  <option key={row.metric} value={row.metric}>
                    {labels[row.metric] ?? row.metric}
                  </option>
                ))}
              </select>
            </label>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[770px] text-left text-sm">
                <thead>
                  <tr className="border-b text-xs text-muted-foreground">
                    <th className="py-2">División</th>
                    <th>Industria</th>
                    <th>IC medio</th>
                    <th>ICIR</th>
                    <th>Trimestres</th>
                    <th>IC positivo</th>
                    <th>Soporte</th>
                    {factor.sic_divisions[0]?.windows.map((window) => (
                      <th key={window.period}>IC {window.period}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {factor.sic_divisions.map((row) => (
                    <tr key={row.division} className="border-b last:border-0">
                      <td className="py-2">{row.division}</td>
                      <td>{row.name}</td>
                      <td>{number(row.ic_mean)}</td>
                      <td>{number(row.icir)}</td>
                      <td>{row.n_periods}</td>
                      <td>{percentage(row.positive_fraction)}</td>
                      <td>{row.status === 'sufficient_periods' ? 'Suficiente' : 'Insuficiente'}</td>
                      {row.windows.map((window) => (
                        <td key={window.period}>{number(window.ic_mean)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer font-medium">
            Cobertura y periodos no estimables · SIC
          </summary>
          <p className="mt-2 text-xs text-muted-foreground">
            Las fechas sin IC se conservan en el artefacto, sin agruparlas ni imputarlas.
          </p>
          <div className="mt-3 max-h-72 overflow-auto">
            <table className="w-full min-w-[540px] text-left text-xs">
              <thead>
                <tr className="border-b">
                  <th className="py-2">Fecha</th>
                  <th>Estrato</th>
                  <th>Elegibles</th>
                  <th>Clasificadas</th>
                  <th>Cobertura</th>
                </tr>
              </thead>
              <tbody>
                {data.coverage.map((row) => (
                  <tr key={`${row.date}-${row.stratum}`} className="border-b last:border-0">
                    <td className="py-1">{row.date}</td>
                    <td>{row.stratum}</td>
                    <td>{row.n_eligible}</td>
                    <td>{row.n_classified}</td>
                    <td>{percentage(row.classified_fraction)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {[
            ['sector_ic.csv', 'IC por industria y trimestre'],
            ['coverage.csv', 'Cobertura y exclusiones'],
            ['factor_coverage.csv', 'Cobertura por señal'],
          ].map(([name, label]) => (
            <a
              key={name}
              className="text-primary underline"
              href={exportBase + name}
              download={name}
            >
              Descargar {label}
            </a>
          ))}
        </div>
      </div>
      <p className="break-all border-t pt-3 text-xs text-muted-foreground">
        Factor Zoo SHA-256: {data.factor_zoo_sha256} · SIC SHA-256: {data.sic_sha256}
      </p>
    </section>
  );
}
