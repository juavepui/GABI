import { useQuery } from '@tanstack/react-query';
import { getJobResult } from '@/shared/api/client';
import { useJob } from '@/shared/api/use-job';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Term } from '@/shared/ui/term';
import { formatNumber } from '@/shared/lib/format';
import { metricLabel } from '@/shared/lib/metric-labels';
import { HealthStatus, RunButton, Section, Table } from './data-health';

type Source = [string, string] | null;
type Cause = {
  metric: string;
  block: string;
  impact: number;
  live_value: number | null;
  historical_value: number | null;
  live_pct: number | null;
  historical_pct: number | null;
  missing: 'live' | 'historical' | null;
  live_source: Source;
  historical_source: Source;
  historical_period_end: string | null;
};
type Parity = {
  as_of: string;
  model_id: string;
  agreement: 'very_similar' | 'similar' | 'different' | null;
  companies: { live: number; historical: number; universe: number; both_scored: number };
  spearman: number | null;
  top_n: number;
  top_overlap: number | null;
  only_live_top: string[];
  only_historical_top: string[];
  blocks: Record<string, number | null>;
  metrics: {
    metric: string;
    block: string;
    live_available: number;
    historical_available: number;
    spearman: number | null;
    live_source: Source;
    historical_source: Source;
  }[];
  largest_differences: {
    symbol: string;
    live_rank: number;
    historical_rank: number;
    rank_change: number;
    cause: Cause | null;
  }[];
};

const BLOCKS: Record<string, string> = {
  value: 'Valoración (si está barata)',
  quality: 'Calidad del negocio',
  momentum: 'Tendencia del precio',
  risk: 'Riesgo',
};
const SOURCES: Record<string, string> = {
  yahoo: 'Yahoo',
  sec_10k: 'SEC (10-K)',
  prices: 'Precios guardados',
};
const PERIODS: Record<string, string> = {
  ttm: 'últimos 12 meses',
  mrq: 'último trimestre',
  snapshot: 'dato del día',
  fiscal_year: 'último ejercicio anual',
  fiscal_years_3: '3 últimos ejercicios',
  '6m': '6 meses',
  '12m': '12 meses',
  '200d': '200 días',
  cached_history: 'todo el histórico',
};
const VERDICTS: Record<string, string> = {
  very_similar:
    'Los dos rankings ordenan las empresas casi igual. Lo que se comprobó con datos del pasado se parece mucho a lo que hace la app, aunque eso no garantiza que vaya a funcionar en el futuro.',
  similar:
    'Los dos rankings se parecen, pero con diferencias apreciables. Lo comprobado con datos del pasado solo vale a medias para el orden que ves en la app.',
  different:
    'Los dos rankings ordenan las empresas de forma bastante distinta. Lo comprobado con datos del pasado dice poco del orden que ves en la app.',
};

const two = (value: number | null | undefined) => formatNumber(value, { digits: 2 });
const source = (value: Source) =>
  value ? `${SOURCES[value[0]] ?? value[0]}, ${PERIODS[value[1]] ?? value[1]}` : '—';

function causeText(cause: Cause | null) {
  if (!cause)
    return 'Sus datos coinciden; cambia de puesto porque otras empresas se movieron a su alrededor.';
  const name = metricLabel(cause.metric);
  if (cause.missing === 'live') return `${name}: falta en la app y el histórico sí lo tiene.`;
  if (cause.missing === 'historical') return `${name}: lo tiene la app y falta en el histórico.`;
  return `${name}: ${two(cause.live_value)} en la app frente a ${two(cause.historical_value)} en el histórico (puesto en su sector ${formatNumber(cause.live_pct, { digits: 0 })} frente a ${formatNumber(cause.historical_pct, { digits: 0 })} sobre 100).`;
}

function Result({ data }: { data: Parity }) {
  const top = data.top_overlap == null ? null : Math.round(data.top_overlap * data.top_n);
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Fecha {data.as_of} · modelo {data.model_id} · {data.companies.both_scored} empresas con
        puntuación en los dos cálculos, de {data.companies.universe}.
      </p>
      {data.agreement ? (
        <p className="rounded-md border p-3">
          <strong>{VERDICTS[data.agreement]}</strong> Si te parece demasiada diferencia, la solución
          es una versión nueva del modelo que use también en la app los datos de la SEC. Es una
          decisión aparte: esta comparación no cambia nada del ranking.
        </p>
      ) : (
        <p className="rounded-md border p-3">
          No hay suficientes empresas con puntuación en los dos cálculos para compararlos. Suele
          pasar cuando faltan datos de la SEC: descárgalos y vuelve a comparar.
        </p>
      )}
      <dl className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">
            <Term k="spearman">Acuerdo de orden</Term>
          </dt>
          <dd className="mt-1 text-base font-semibold tabular-nums">
            {two(data.spearman)} <span className="text-xs font-normal">sobre 1</span>
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">Top-{data.top_n} en común</dt>
          <dd className="mt-1 text-base font-semibold tabular-nums">
            {top == null ? '—' : `${top} de ${data.top_n} empresas`}
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">Solo en el Top-{data.top_n} de la app</dt>
          <dd className="mt-1 text-sm font-semibold">
            {data.only_live_top.join(', ') || 'Ninguna'}
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">Solo en el Top-{data.top_n} histórico</dt>
          <dd className="mt-1 text-sm font-semibold">
            {data.only_historical_top.join(', ') || 'Ninguna'}
          </dd>
        </div>
      </dl>
      <Table
        label="Acuerdo por apartado de la puntuación"
        columns={[
          ['block', 'Apartado'],
          ['spearman', 'Acuerdo de orden (de −1 a 1)'],
        ]}
        rows={Object.entries(data.blocks).map(([block, value]) => ({
          block: BLOCKS[block] ?? block,
          spearman: two(value),
        }))}
      />
      <Table
        label="De dónde sale cada métrica en cada cálculo"
        columns={[
          ['metric', 'Métrica'],
          ['live', 'En la app'],
          ['historical', 'En el cálculo histórico'],
          ['spearman', 'Acuerdo de orden'],
        ]}
        rows={data.metrics.map((row) => ({
          metric: metricLabel(row.metric),
          live: `${source(row.live_source)} (${row.live_available} empresas)`,
          historical: `${source(row.historical_source)} (${row.historical_available} empresas)`,
          spearman: two(row.spearman),
        }))}
      />
      <Table
        label="Empresas que más cambian de puesto"
        columns={[
          ['symbol', 'Empresa'],
          ['live', 'Puesto en la app'],
          ['historical', 'Puesto en el histórico'],
          ['cause', 'Qué lo explica sobre todo'],
        ]}
        rows={data.largest_differences.map((row) => ({
          symbol: row.symbol,
          live: String(row.live_rank),
          historical: String(row.historical_rank),
          cause: causeText(row.cause),
        }))}
      />
    </div>
  );
}

/** «Ranking de la app frente al cálculo histórico» (#291): an explicit local job that changes nothing. */
export function RankingParity() {
  const { start, job } = useJob('ranking-parity');
  const result = useQuery({
    queryKey: ['job', job.data?.id, 'result'],
    queryFn: ({ signal }) => getJobResult(job.data!.id, signal) as Promise<Parity>,
    enabled: job.data?.status === 'succeeded',
  });
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  return (
    <Section title="Ranking de la app frente al cálculo histórico">
      <p>
        La app puntúa la valoración y parte de la calidad con datos de Yahoo de los{' '}
        <Term k="ttm_vs_annual">últimos 12 meses</Term>. Las pruebas con datos del pasado usan el
        informe anual de la SEC (10-K). Aquí se calculan los dos rankings para hoy, con las mismas
        empresas y los mismos pesos, para ver cuánto se parecen.
      </p>
      <HowToRead>
        El ranking de la app es el que ves en Mercado. El histórico es el que usan las pruebas con
        datos del pasado, aplicado hoy: solo usa lo que la SEC ya había publicado y el precio del
        día. Para cada empresa que cambia de puesto se indica la métrica que más mueve su
        puntuación, con su valor en cada cálculo y de dónde sale. Solo se lee lo guardado en tu
        equipo; no se descarga nada ni se cambia el ranking.
      </HowToRead>
      <RunButton running={running} onClick={() => start.mutate({ kind: 'ranking_parity' })}>
        Comparar los dos rankings
      </RunButton>
      <HealthStatus state={{ start, job, result }} failure="No se pudo comparar los rankings." />
      {result.data && <Result data={result.data} />}
    </Section>
  );
}
