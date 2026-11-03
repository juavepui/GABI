import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  companyEvidenceDownload,
  getCompanyEvidence,
  getEvidenceTop,
  getRankingStability,
} from '@/shared/api/client';
import { EvidenceTable } from '@/shared/ui/evidence-table';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { Folded } from '@/shared/ui/folded';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatNumber, formatPercent } from '@/shared/lib/format';

// The 13 scored metrics (scoring.SCORE_METRICS), with the labels of the old pages.
const METRIC_LABELS: Record<string, string> = {
  pe: 'PER',
  pb: 'Precio / valor contable',
  ev_ebitda: 'EV/EBITDA',
  roic: 'ROIC',
  operating_margin: 'Margen operativo',
  revenue_cagr_3y: 'Crecimiento de ventas (3 años)',
  fcf_cagr_3y: 'Crecimiento de la caja libre (3 años)',
  momentum_12m: 'Subida en 12 meses',
  rel_strength_6m: 'Subida frente al mercado (6 meses)',
  price_vs_sma200: 'Precio frente a su media de 200 días',
  debt_to_equity: 'Deuda/Patrimonio',
  volatility: 'Volatilidad anualizada (todo el histórico)',
  max_drawdown: 'Caída máxima (todo el histórico)',
};
const label = (metric: string) => METRIC_LABELS[metric] ?? metric;
const num = (value: number | null | undefined, digits = 1) => formatNumber(value, { digits });
const pct = (value: number | null | undefined, digits = 0) => formatPercent(value, { digits });

export function CompanyEvidenceDetail({ symbol }: { symbol: string }) {
  const [sicMetric, setSicMetric] = useState('');
  const query = useQuery({
    queryKey: ['market', 'evidence', symbol],
    queryFn: ({ signal }) => getCompanyEvidence(symbol, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const e = query.data;
  const industry = e.factors.filter((factor) => factor.sic_division_stability.length > 0);
  const sic = industry.find((factor) => factor.metric === sicMetric) ?? industry[0];
  return (
    <div className="space-y-3 text-sm" role="region" aria-label={`Evidencia de ${e.symbol}`}>
      <p>
        <span className="text-muted-foreground">Confianza en las pruebas que la respaldan: </span>
        <strong>{e.confidence_level}</strong>
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="font-medium">A favor</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {e.reasons_for.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-medium">En contra y limitaciones</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {e.reasons_against.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      </div>
      {e.factors.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs" aria-label="Factores del score">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Métrica</th>
                <th>Apartado</th>
                <th>Posición frente al resto (0–100)</th>
                <th>¿Juega a favor?</th>
                <th>Peso en la puntuación</th>
                <th>Puntos que aporta</th>
                <th>¿Comprobada con datos del pasado?</th>
                <th>IC medio (técnico)</th>
                <th>p Holm (técnico)</th>
              </tr>
            </thead>
            <tbody>
              {e.factors.map((factor) => (
                <tr key={factor.metric} className="border-b last:border-0">
                  <td className="py-1.5">{label(factor.metric)}</td>
                  <td>{factor.family}</td>
                  <td>{num(factor.percentile)}</td>
                  <td>{factor.supports_candidate ? 'Sí' : 'No'}</td>
                  <td>{pct(factor.effective_weight, 1)}</td>
                  <td>{num(factor.contribution_points, 2)}</td>
                  <td>{factor.statistically_supported ? 'Sí' : 'No'}</td>
                  <td>{num(factor.mean_ic, 4)}</td>
                  <td>{num(factor.p_holm, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        Una posición alta (cerca de 100) significa que la empresa sale mejor que la mayoría en esa
        métrica. La columna «¿Comprobada…?» dice si esa métrica ha demostrado, con una prueba
        estadística exigente, que ayudaba a elegir mejores acciones en el pasado. Que no esté
        comprobada no quiere decir que no sirva, solo que aún no hay pruebas. Nada de esto cambia el
        ranking.
      </p>
      {sic && (
        <details className="rounded-lg border p-3">
          <summary className="cursor-pointer font-medium">
            ¿Funciona igual en todas las industrias? (técnico)
          </summary>
          <label className="mt-2 grid w-fit gap-1">
            Factor · diagnóstico SIC
            <NativeSelect value={sic.metric} onChange={(event) => setSicMetric(event.target.value)}>
              {industry.map((factor) => (
                <NativeSelectOption key={factor.metric} value={factor.metric}>
                  {label(factor.metric)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
          <table className="mt-2 text-left text-xs" aria-label="Estabilidad por industria">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2 pr-4">División SIC</th>
                <th className="pr-4">Industria</th>
                <th className="pr-4">IC medio</th>
                <th className="pr-4">Trimestres</th>
                <th>Soporte temporal</th>
              </tr>
            </thead>
            <tbody>
              {sic.sic_division_stability.map((row) => (
                <tr key={row.group} className="border-b last:border-0">
                  <td className="py-1 pr-4">{row.group}</td>
                  <td className="pr-4">{row.name ?? '—'}</td>
                  <td className="pr-4">{num(row.ic_mean, 4)}</td>
                  <td className="pr-4">{row.n_periods ?? '—'}</td>
                  <td>{row.status === 'sufficient_periods' ? 'Suficiente' : 'Insuficiente'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted-foreground">
            Usa la clasificación de industrias SIC de la SEC, distinta de los sectores que ves en el
            ranking. Es un análisis del pasado: no confirma nada por sí solo ni sube la confianza.
          </p>
        </details>
      )}
      <p className="text-xs text-muted-foreground">
        Fase del registro: {e.collection_stage} · evidencia: {e.evidence_stage} · reglas:{' '}
        {e.rules_version}
      </p>
      {e.research_details && (
        <details className="rounded-lg border p-3">
          <summary className="cursor-pointer font-medium">Detalle técnico (Research)</summary>
          <pre className="mt-2 max-h-96 overflow-auto text-xs">
            {JSON.stringify(e.research_details, null, 2)}
          </pre>
        </details>
      )}
      <a className="text-primary underline" href={companyEvidenceDownload(e.symbol)} download>
        Descargar evidencia de la candidata
      </a>
    </div>
  );
}

function EvidenceContent() {
  const [selected, setSelected] = useState<string | null>(null);
  const top = useQuery({
    queryKey: ['market', 'evidence'],
    queryFn: ({ signal }) => getEvidenceTop(false, signal),
  });
  return (
    <section className="space-y-3" aria-label="Evidencia">
      <p className="text-xs text-muted-foreground">
        Para cada una de las 20 primeras: su puntuación (cómo sale según las métricas), cuántos
        datos tiene y la confianza en las pruebas que la respaldan (BAJA, MEDIA o ALTA, según unas
        reglas fijas). La confianza no es la probabilidad de que suba.
      </p>
      {top.isPending && <LoadingState />}
      {top.isError && <ErrorState error={top.error} retry={() => void top.refetch()} />}
      {top.data && !top.data.available && (
        <p className="text-sm text-muted-foreground">
          Todavía no hay empresas con datos suficientes para mostrar esto.
        </p>
      )}
      {top.data?.available && top.data.rows.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Ninguna empresa cumple aún los requisitos para entrar entre las 20 primeras. Puedes ver el
          análisis de cada una en su ficha.
        </p>
      )}
      {top.data && top.data.rows.length > 0 && (
        <>
          <EvidenceTable rows={top.data.rows} onSelect={setSelected} />
          <details className="rounded-lg border p-3" open={selected != null}>
            <summary className="cursor-pointer font-medium">
              Por qué tiene este nivel de confianza
            </summary>
            <label className="mt-2 grid w-fit gap-1 text-sm">
              Empresa
              <NativeSelect
                value={selected ?? top.data.rows[0].symbol}
                onChange={(event) => setSelected(event.target.value)}
              >
                {top.data.rows.map((row) => (
                  <NativeSelectOption key={row.symbol} value={row.symbol}>
                    {row.symbol}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </label>
            <div className="mt-3">
              <CompanyEvidenceDetail symbol={selected ?? top.data.rows[0].symbol} />
            </div>
          </details>
        </>
      )}
    </section>
  );
}

function Records({
  title,
  rows,
}: {
  title: string;
  rows: Record<string, string | number | null | undefined>[];
}) {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  return (
    <div className="max-h-80 overflow-auto">
      <table className="w-full text-left text-xs" aria-label={title}>
        <thead className="sticky top-0 bg-card">
          <tr className="border-b text-muted-foreground">
            {columns.map((column) => (
              <th key={column} className="py-2 pr-3">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b last:border-0">
              {columns.map((column) => (
                <td key={column} className="py-1 pr-3">
                  {typeof row[column] === 'number' ? num(row[column] as number, 4) : row[column]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StabilityContent() {
  const query = useQuery({
    queryKey: ['market', 'ranking-stability'],
    queryFn: ({ signal }) => getRankingStability(signal),
  });
  return (
    <div className="space-y-3" role="region" aria-label="Estabilidad del ranking">
      {query.isPending && <LoadingState />}
      {query.isError && <ErrorState error={query.error} retry={() => void query.refetch()} />}
      {query.data && !query.data.available && (
        <p className="text-muted-foreground">{query.data.message}</p>
      )}
      {query.data?.summary && (
        <>
          {query.data.summary.stability_score == null ? (
            <p className="text-muted-foreground">
              Hay muy pocas empresas para medir si las 20 primeras cambian mucho.
            </p>
          ) : (
            <p className="text-xl font-semibold">
              De media, siguen entre las 20 primeras: {num(query.data.summary.stability_score)} %
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Hemos recalculado el ranking cambiando un poco los pesos de cada apartado (
            {query.data.summary.perturbations} variantes sobre {query.data.summary.eligible}{' '}
            empresas; {query.data.summary.omitted_infeasible} variantes descartadas por salirse de
            los límites). Si una empresa sigue entre las 20 primeras en casi todas, su posición es
            sólida; si entra y sale, depende mucho de detalles. No dice nada de cuánto subirá.
          </p>
          {!query.data.summary.sectors_complete && (
            <p className="text-xs text-muted-foreground">
              A algunas empresas les falta el sector, así que el reparto por sectores está
              incompleto.
            </p>
          )}
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-left text-xs" aria-label="Persistencia por empresa">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b text-muted-foreground">
                  <th className="py-2">Empresa</th>
                  <th>Posición</th>
                  <th>Mejor posición</th>
                  <th>Peor posición</th>
                  <th>Veces entre las 20 primeras</th>
                  <th>Diagnóstico</th>
                </tr>
              </thead>
              <tbody>
                {query.data.companies.map((row) => (
                  <tr key={String(row.symbol)} className="border-b last:border-0">
                    <td className="py-1">{row.symbol}</td>
                    <td>{row.base_rank}</td>
                    <td>{row.rank_min}</td>
                    <td>{row.rank_max}</td>
                    <td>{pct(row.top20_inclusion as number | null)}</td>
                    <td>{row.diagnosis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {query.data.mode === 'RESEARCH' && (
            <>
              <p className="text-xs text-muted-foreground">
                Research: diagnóstico de los pesos actuales, incluidos los experimentales; no se
                elige una variante por retorno.
              </p>
              <Records title="Métricas por perturbación" rows={query.data.metrics} />
              <Records title="Pesos de cada perturbación" rows={query.data.perturbations} />
            </>
          )}
        </>
      )}
    </div>
  );
}

export function RankingEvidence() {
  return (
    <Folded
      title="¿Cuánto fiarse de las 20 primeras? · pruebas que las respaldan"
      className="mt-6 rounded-xl border bg-card p-5 text-sm"
    >
      <EvidenceContent />
    </Folded>
  );
}

export function RankingStabilityPanel() {
  return (
    <Folded
      title="¿Es estable el ranking? · qué pasa si cambian un poco los pesos"
      className="mt-6 rounded-xl border bg-card p-5 text-sm"
    >
      <StabilityContent />
    </Folded>
  );
}
