import { useQuery } from '@tanstack/react-query';
import { getJobResult } from '@/shared/api/client';
import { useJob } from '@/shared/api/use-job';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Term } from '@/shared/ui/term';
import { formatNumber } from '@/shared/lib/format';
import { metricLabel } from '@/shared/lib/metric-labels';
import { HealthStatus, RunButton, Section, Table } from './data-health';

type Mark = {
  symbol: string;
  rule: 'range' | 'jump' | 'market_cap';
  field: string;
  value: number | null;
  reason: string;
  date?: string;
};
type Report = {
  policy: string;
  model_id: string;
  applied: boolean;
  companies: number;
  affected: number;
  by_rule: Record<string, number>;
  blocks: string[];
  marks: Mark[];
  total_marks: number;
};

const RULES: Record<string, string> = {
  range: 'Valor imposible',
  jump: 'Salto de precio sin split',
  market_cap: 'Capitalización que no cuadra con la SEC',
};
const FIELDS: Record<string, string> = {
  price: 'Precio',
  market_cap: 'Capitalización',
  roe: 'ROE',
  roa: 'ROA',
  gross_margin: 'Margen bruto',
  profit_margin: 'Margen neto',
  peg: 'PEG',
  ps: 'Precio / ventas',
  current_ratio: 'Liquidez corriente',
  revenue_growth_yoy: 'Crecimiento de ventas',
  earnings_growth_yoy: 'Crecimiento del beneficio',
  dividend_yield: 'Rentabilidad por dividendo',
  beta: 'Beta',
};
const field = (key: string) => FIELDS[key] ?? metricLabel(key);

function Result({ data }: { data: Report }) {
  const model = data.applied
    ? `El modelo activo (${data.model_id}) no usa para puntuar los valores imposibles ni, tras un salto de precio, las métricas de precio: cuentan como datos que faltan. La capitalización solo se informa.`
    : `El modelo activo (${data.model_id}) puntúa los valores tal y como vienen, igual que en la prueba con datos del pasado: estas marcas son solo un aviso para revisar.`;
  return (
    <div className="space-y-3">
      <p className="rounded-md border p-3">
        <strong>
          {data.affected === 0
            ? `No hay ningún dato imposible ni sospechoso en las ${data.companies} empresas.`
            : `${data.affected} de ${data.companies} empresas tienen algún dato marcado (${data.total_marks} en total).`}
        </strong>{' '}
        {model}
      </p>
      {data.total_marks > 0 && (
        <Table
          label="Datos marcados por tipo"
          columns={[
            ['rule', 'Tipo'],
            ['count', 'Datos'],
          ]}
          rows={Object.entries(data.by_rule).map(([rule, count]) => ({
            rule: RULES[rule] ?? rule,
            count: String(count),
          }))}
        />
      )}
      {data.marks.length > 0 && (
        <Table
          label="Datos marcados"
          columns={[
            ['symbol', 'Empresa'],
            ['field', 'Dato'],
            ['value', 'Valor'],
            ['reason', 'Motivo'],
          ]}
          rows={data.marks.map((mark) => ({
            symbol: mark.symbol,
            field: field(mark.field) + (mark.date ? ` (${mark.date})` : ''),
            value: formatNumber(mark.value, { digits: 2 }),
            reason: mark.reason,
          }))}
        />
      )}
      {data.total_marks > data.marks.length && (
        <p className="text-xs text-muted-foreground">
          Se muestran {data.marks.length} de {data.total_marks}.
        </p>
      )}
    </div>
  );
}

/** «Datos imposibles o sospechosos» (#295): an explicit local job over the cached data. */
export function InputChecks() {
  const { start, job } = useJob('input-checks');
  const result = useQuery({
    queryKey: ['job', job.data?.id, 'result'],
    queryFn: ({ signal }) => getJobResult(job.data!.id, signal) as Promise<Report>,
    enabled: job.data?.status === 'succeeded',
  });
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  return (
    <Section title="Datos imposibles o sospechosos">
      <p>
        Si entra un dato imposible, el ranking puede subir o bajar una empresa sin que nadie lo vea.
        Esta comprobación busca en los datos guardados los valores que no son creíbles (
        <Term k="input_checks">controles de datos</Term>).
      </p>
      <HowToRead>
        Bloquean la descarga, y nunca llegan a guardarse, los precios no positivos, los máximos o
        mínimos incoherentes y las sesiones duplicadas. Solo se marcan, con su motivo: un dato de
        Yahoo fuera de su rango creíble (por ejemplo, un PER por encima de 1.000 o un margen por
        encima del 100 %), un movimiento de más del 50 % en un día sin split registrado, y una
        capitalización que difiere más de un 50 % de precio × acciones de la SEC. Esta última solo
        se informa, porque las empresas con varias clases de acciones darían falsos avisos. No se
        descarga nada.
      </HowToRead>
      <RunButton running={running} onClick={() => start.mutate({ kind: 'input_checks' })}>
        Buscar datos imposibles
      </RunButton>
      <HealthStatus state={{ start, job, result }} failure="No se pudo comprobar los datos." />
      {result.data && <Result data={result.data} />}
    </Section>
  );
}
