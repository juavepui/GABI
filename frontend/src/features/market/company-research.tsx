import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createJob,
  getCompanyFilingChanges,
  getCompanyResearch,
  getJob,
  getJobResult,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Folded } from '@/shared/ui/folded';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { dateLabel } from '@/shared/lib/format';

const EVENT_LABELS: Record<string, string> = {
  earnings: 'Earnings',
  ex_dividend: 'Ex-dividendo',
  dividend_payment: 'Pago de dividendo',
};
const FILING_LABELS: Record<string, string> = {
  revenue: 'Ingresos',
  operating_margin: 'Margen operativo',
  gross_margin: 'Margen bruto',
  fcf: 'Flujo de caja libre',
  debt: 'Deuda a largo plazo',
  cash: 'Caja',
  roic: 'ROIC',
};
const num = (value: number | null | undefined, digits = 2) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value);
const pct = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1, signDisplay: 'always' }).format(
        value * 100,
      ) + ' %';

/** Explicit network sync of one company's dataset, as the old Ficha buttons, run by the worker. */
function SyncButton({
  symbol,
  dataset,
  label,
}: {
  symbol: string;
  dataset: 'surprises' | 'estimates';
  label: string;
}) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () =>
      createJob({
        kind: 'company_sync',
        company: { symbol, dataset },
        idempotency_key: 'company:' + crypto.randomUUID(),
      }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: ({ signal }) => getJob(jobId!, signal),
    enabled: jobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const result = useQuery({
    queryKey: ['job', jobId, 'result'],
    queryFn: ({ signal }) =>
      getJobResult(jobId!, signal) as Promise<{ synced: boolean; reason: string | null }>,
    enabled: job.data?.status === 'succeeded',
  });
  const synced = result.data?.synced === true;
  useEffect(() => {
    if (synced) void queryClient.invalidateQueries({ queryKey: ['market', 'research', symbol] });
  }, [synced, symbol, queryClient]);
  return (
    <div className="space-y-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={start.isPending || ['queued', 'running'].includes(job.data?.status ?? '')}
        onClick={() => start.mutate()}
      >
        {label}
      </Button>
      {start.isError && <ErrorState error={start.error} retry={() => start.reset()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <p className="text-xs text-muted-foreground" role="status">
          Descarga en curso: {job.data.phase} ({job.data.status}).
        </p>
      )}
      {result.data &&
        (result.data.synced ? (
          <p className="text-xs" role="status">
            Sincronizado.
          </p>
        ) : (
          <p className="text-xs text-destructive" role="status">
            No se pudo sincronizar: {String(result.data.reason)}
          </p>
        ))}
    </div>
  );
}

export function CompanyResearch({ symbol }: { symbol: string }) {
  const query = useQuery({
    queryKey: ['market', 'research', symbol],
    queryFn: ({ signal }) => getCompanyResearch(symbol, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  const estimate = data.estimate;
  const revision = data.revision_90d as {
    change?: number;
    change_pct?: number;
    actual_lookback_days?: number;
  } | null;
  return (
    <div className="space-y-4">
      <section
        className="rounded-xl border bg-card p-5 text-sm"
        aria-label="Próximos catalizadores"
      >
        <h2 className="text-lg font-semibold">Próximos catalizadores</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Fechas conocidas, no una predicción del precio: contexto para no llegar a un buen score
          sin saber que hay resultados mañana. No entra en el score.
        </p>
        {data.events.length === 0 ? (
          <p className="mt-2 text-muted-foreground">
            Sin próximos eventos conocidos en los datos cacheados de Yahoo Finance.
          </p>
        ) : (
          <ul className="mt-2 space-y-1">
            {data.events.map((event) => (
              <li key={event.event_type + event.event_date}>
                <strong>{EVENT_LABELS[event.event_type]}</strong>: {dateLabel(event.event_date)}
                {event.range_end ? ` – ${dateLabel(event.range_end)}` : ''} (fecha{' '}
                {event.is_estimate ? 'estimada' : 'confirmada'}, en {event.days_until} días) ·
                fuente: {event.source}
              </li>
            ))}
          </ul>
        )}
      </section>
      <Folded title="Historial de sorpresas de resultados (dato de investigación, no puntuado)">
        <p className="text-xs text-muted-foreground">
          EPS estimado frente a reportado y el salto de precio entre el cierre anterior y el
          posterior a los resultados. Se guarda para poder validarlo como factor candidato; hoy no
          influye en el score.
        </p>
        <SyncButton
          symbol={symbol}
          dataset="surprises"
          label="Sincronizar historial de resultados"
        />
        {data.surprises.length === 0 ? (
          <p className="text-muted-foreground">Sin historial sincronizado todavía.</p>
        ) : (
          <table className="w-full text-left text-xs" aria-label="Sorpresas de resultados">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Fecha</th>
                <th>EPS estimado</th>
                <th>EPS reportado</th>
                <th>Sorpresa %</th>
                <th>Reacción precio %</th>
              </tr>
            </thead>
            <tbody>
              {data.surprises.map((row) => (
                <tr key={row.earnings_date} className="border-b last:border-0">
                  <td className="py-1">{row.earnings_date}</td>
                  <td>{num(row.eps_estimate)}</td>
                  <td>{num(row.eps_reported)}</td>
                  <td>{num(row.surprise_pct, 1)}</td>
                  <td>{num(row.price_reaction_pct, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Folded>
      <Folded title="Estimaciones de consenso (experimental, no puntuado)">
        <p className="text-xs text-muted-foreground">
          Consenso de analistas de Yahoo Finance, sin licencia formal. Yahoo no ofrece un histórico
          point-in-time: GABI guarda cada captura con su fecha real, así que el histórico propio
          solo crece hacia delante. No entra en el score sin validación explícita en Investigación.
        </p>
        <SyncButton symbol={symbol} dataset="estimates" label="Sincronizar estimaciones" />
        {estimate == null ? (
          <p className="text-muted-foreground">Sin estimaciones sincronizadas todavía.</p>
        ) : (
          <>
            <dl className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border p-3">
                <dt
                  className="text-xs text-muted-foreground"
                  title={`Rango ${num(estimate.eps_low)}–${num(estimate.eps_high)}, ${estimate.eps_analysts ?? '—'} analistas.`}
                >
                  EPS consenso (trimestre actual)
                </dt>
                <dd className="text-xl font-semibold">{num(estimate.eps_avg)}</dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt
                  className="text-xs text-muted-foreground"
                  title="(máximo − mínimo) / medio: proxy del desacuerdo entre analistas."
                >
                  Dispersión del consenso
                </dt>
                <dd className="text-xl font-semibold">
                  {estimate.eps_dispersion_pct == null
                    ? '—'
                    : num(estimate.eps_dispersion_pct * 100, 1) + ' %'}
                </dd>
              </div>
              <div className="rounded-lg border p-3">
                <dt className="text-xs text-muted-foreground">Revisiones netas (30 días)</dt>
                <dd className="text-xl font-semibold">
                  {estimate.revised_up_30d != null && estimate.revised_down_30d != null
                    ? estimate.revised_up_30d - estimate.revised_down_30d
                    : '—'}
                </dd>
              </div>
            </dl>
            <p className="text-xs text-muted-foreground">
              Capturado el {estimate.captured_at} · fuente: {estimate.source}
            </p>
            <p className="text-xs text-muted-foreground">
              {revision?.change != null
                ? `Cambio propio de GABI en el consenso EPS en los últimos ${revision.actual_lookback_days} días (entre capturas reales): ${num(revision.change)} (${pct(revision.change_pct)}).`
                : 'Aún sin margen suficiente en el histórico propio de GABI para medir un cambio.'}
            </p>
          </>
        )}
      </Folded>
    </div>
  );
}

function FilingChangesContent({ symbol }: { symbol: string }) {
  const query = useQuery({
    queryKey: ['market', 'filing-changes', symbol],
    queryFn: ({ signal }) => getCompanyFilingChanges(symbol, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return (
    <>
      <p className="text-xs text-muted-foreground">
        «Cambio material» es una regla explícita de GABI (umbrales sobre cada métrica), no una
        conclusión de inversión. Compara solo métricas fundamentales ya cacheadas; no analiza el
        texto del filing.
      </p>
      {query.data.results.map((result) => (
        <div key={result.form} className="space-y-1">
          <p className="font-medium">
            {result.form}
            {result.previous && result.current
              ? `: ${result.previous.filed_date} → ${result.current.filed_date}`
              : ''}
          </p>
          {result.rows.length === 0 ? (
            <p className="text-muted-foreground">{result.reason}</p>
          ) : (
            <table className="w-full text-left text-xs" aria-label={`Cambios ${result.form}`}>
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="py-2">Métrica</th>
                  <th>Anterior</th>
                  <th>Actual</th>
                  <th>Cambio</th>
                  <th>Severidad</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.metric} className="border-b last:border-0">
                    <td className="py-1">{FILING_LABELS[row.metric] ?? row.metric}</td>
                    <td>{num(row.previous_value)}</td>
                    <td>{num(row.current_value)}</td>
                    <td>{row.pct_change != null ? pct(row.pct_change) : num(row.abs_change)}</td>
                    <td>
                      {row.severity === 'MATERIAL'
                        ? row.direction === 'improvement'
                          ? 'Material · mejora'
                          : 'Material · deterioro'
                        : 'Informativo'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </>
  );
}

export function FilingChanges({ symbol }: { symbol: string }) {
  return (
    <Folded
      title="Qué cambió respecto al filing anterior (10-K y 10-Q)"
      className="mb-6 rounded-xl border bg-card p-5 text-sm"
    >
      <FilingChangesContent symbol={symbol} />
    </Folded>
  );
}
