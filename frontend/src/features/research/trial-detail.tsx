import { lazy, Suspense } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BadgeCheck, CircleAlert } from 'lucide-react';
import { getResearchTrial } from '@/shared/api/client';
import type { TrialDetail as Detail, TrialRow } from '@/shared/api/generated/types.gen';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { formatMoney, formatNumber, formatPercent } from '@/shared/lib/format';

const TrialReturnsChart = lazy(() => import('./trial-returns-chart'));

function format(row: TrialRow): string {
  const { value, unit } = row;
  if (value == null || value === '') return '—';
  if (unit === 'boolean' || typeof value === 'boolean') return value ? 'Sí' : 'No';
  if (typeof value === 'string') return value;
  const number = (digits: number) => formatNumber(value, { digits });
  if (unit === 'fraction') return formatPercent(value, { digits: 2 });
  if (unit === 'USD') return formatMoney(value);
  if (unit === 'count') return number(0);
  return number(Math.abs(value) < 1 ? 4 : 3);
}

function Rows({ title, rows }: { title: string; rows: TrialRow[] }) {
  if (!rows.length) return null;
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        {rows.map((row, index) => (
          <div key={row.path + index} className="flex justify-between gap-3 border-b py-1">
            <dt className="text-muted-foreground">{row.path}</dt>
            <dd className="text-right font-medium tabular-nums">{format(row)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Sample({ detail }: { detail: Detail }) {
  const sample = detail.observed_sample ?? detail.planned_sample;
  if (!sample) return null;
  return (
    <p className="text-xs text-muted-foreground">
      {detail.observed_sample ? 'Muestra observada' : 'Muestra planificada'}:{' '}
      {Object.entries(sample)
        .map(([key, value]) => `${key} ${String(value)}`)
        .join(' · ')}
    </p>
  );
}

/** What a published trial tested and what it published, as the ledger and its artifacts record it. */
export function TrialDetail({ id }: { id: string }) {
  const detail = useQuery({
    queryKey: ['research', 'trial', id],
    queryFn: ({ signal }) => getResearchTrial(id, signal),
    staleTime: Infinity,
  });
  if (detail.isPending) return <LoadingState />;
  if (detail.isError)
    return <ErrorState error={detail.error} retry={() => void detail.refetch()} />;
  const data = detail.data;
  return (
    <div
      role="region"
      className="space-y-4 rounded-lg border bg-muted/30 p-4"
      aria-label={'Detalle de ' + id}
    >
      <Sample detail={data} />
      <Rows title="Qué se probó (configuración)" rows={data.configuration} />
      {data.result_verified != null && (
        <p
          className={
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ' +
            (data.result_verified
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-amber-100 text-amber-900')
          }
        >
          {data.result_verified ? (
            <BadgeCheck size={14} aria-hidden="true" />
          ) : (
            <CircleAlert size={14} aria-hidden="true" />
          )}
          {data.result_verified
            ? 'Resultado verificado con el hash publicado'
            : 'El fichero no coincide con el hash publicado'}
        </p>
      )}
      <Rows title="Estadísticos publicados" rows={data.statistics} />
      <Rows title="Resultado publicado" rows={data.result} />
      {data.series && data.series.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">
            Rentabilidad publicada por periodo ({data.series.length} periodos)
          </h3>
          <Suspense fallback={<div className="h-48" />}>
            <TrialReturnsChart points={data.series} />
          </Suspense>
        </section>
      )}
      {data.result_note && <p className="text-xs text-muted-foreground">{data.result_note}</p>}
      <p className="text-xs text-muted-foreground">
        Especificación: <code className="break-all">{data.specification_ref}</code>
        {data.result_ref && (
          <>
            {' '}
            · resultado: <code className="break-all">{data.result_ref}</code>
          </>
        )}
      </p>
    </div>
  );
}
