import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getComparisonChecklist } from '@/shared/api/client';
import type {
  ChecklistMedian,
  ComparedChecklist,
  ComparedCriterion,
} from '@/shared/api/generated/types.gen';
import { Badge } from '@/shared/ui/badge';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { reasonText, show, VERDICTS } from './checklist-format';

const SOURCES: Record<ComparedCriterion['source'], string> = {
  sec_10k: 'SEC 10-K · último ejercicio',
  'price+sec': 'Precio actual + SEC 10-K',
  yahoo: 'Yahoo · dato actual',
  'price+yahoo': 'Precio actual + consenso Yahoo',
  prices: 'GABI con precios en caché',
};

function median(item: ChecklistMedian | undefined, what: string): string {
  if (!item) return '—';
  if (item.median == null) return reasonText(item.reason) || '—';
  return `${show(item.median, 'ratio')} (${item.count} ${what})`;
}

function Criterion({ item, company }: { item: ComparedCriterion; company: ComparedChecklist }) {
  const verdict = VERDICTS[item.verdict];
  const multiple = item.key === 'pe' || item.key === 'ev_ebitda';
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium tabular-nums">{show(item.value, item.unit)}</span>
        <Badge variant={verdict.variant}>{verdict.label}</Badge>
      </div>
      {item.reason && item.verdict !== 'pass' && (
        <p className="text-xs text-muted-foreground">{reasonText(item.reason)}</p>
      )}
      {multiple && (
        <p className="text-xs text-muted-foreground">
          Propia: {median(company.history_medians[item.key], 'años')} · Sector:{' '}
          {median(company.sector_medians[item.key], 'pares')}
        </p>
      )}
    </div>
  );
}

function Summary({ company }: { company: ComparedChecklist }) {
  const { passed, evaluated, missing } = company.summary;
  return (
    <span className="tabular-nums">
      {evaluated ? `${passed} de ${evaluated} cumplidos` : 'Sin criterios evaluables'}
      {missing ? (
        <span className="block text-xs text-muted-foreground">{missing} sin dato</span>
      ) : null}
    </span>
  );
}

function Alarms({ company }: { company: ComparedChecklist }) {
  if (!company.active_alarms.length)
    return <span className="text-muted-foreground">Ninguna activa</span>;
  return (
    <ul className="space-y-1 text-xs">
      {company.active_alarms.map((label) => (
        <li key={label}>
          <Badge variant="destructive">{label}</Badge>
        </li>
      ))}
    </ul>
  );
}

/** Checklist digest of each compared company, as its company page's checklist computes it. */
export function ComparisonChecklist({ symbols }: { symbols: string[] }) {
  const query = useQuery({
    queryKey: ['market', 'comparison', 'checklist', symbols],
    queryFn: ({ signal }) => getComparisonChecklist(symbols, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const items = query.data.items;
  const criteria = items[0]?.criteria ?? [];
  const rows: [string, string, (company: ComparedChecklist) => ReactNode][] = [
    ['Checklist', 'Criterios cumplidos de los evaluables', (c) => <Summary company={c} />],
    ['Alarmas', 'Alarmas activas del checklist', (c) => <Alarms company={c} />],
    ...criteria.map((criterion): [string, string, (company: ComparedChecklist) => ReactNode] => [
      criterion.label,
      SOURCES[criterion.source],
      (c) => {
        const item = c.criteria.find((other) => other.key === criterion.key);
        return item ? <Criterion item={item} company={c} /> : '—';
      },
    ]),
  ];
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto" role="region" aria-label="Checklist comparado" tabIndex={0}>
        <table className="w-full min-w-[600px] text-left text-sm">
          <thead>
            <tr className="border-b">
              <th className="pb-3">Criterio</th>
              {items.map((company) => (
                <th className="pb-3" key={company.symbol}>
                  {company.symbol}
                  <span className="mt-1 block text-xs font-normal text-muted-foreground">
                    {company.sector ?? 'Sin sector'}
                    {company.fiscal_year_end
                      ? ' · FY' + company.fiscal_year_end.slice(0, 4)
                      : ' · sin 10-K'}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, source, cell]) => (
              <tr key={label} className="border-b align-top last:border-0">
                <th scope="row" className="py-3 pr-3 font-medium">
                  {label}
                  <span className="block text-xs font-normal text-muted-foreground">{source}</span>
                </th>
                {items.map((company) => (
                  <td key={company.symbol} className="px-3 py-3">
                    {cell(company)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Valores y umbrales del checklist de cada ficha. «Propia» es la mediana del múltiplo de la
        empresa en sus últimos {items[0]?.history_years ?? 5} ejercicios; «Sector», la de las demás
        empresas de su sector en el universo actual, con las mismas fórmulas SEC. Un múltiplo por
        debajo de su referencia no implica que la empresa esté barata. El PER y el EV/EBITDA de
        arriba son los de Yahoo (12 meses); estos se calculan con el último 10-K.
      </p>
    </div>
  );
}
