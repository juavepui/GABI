import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createJob,
  getAnalysisPrompt,
  getCompanyFilingChanges,
  getCompanyInsiders,
  getCompanyResearch,
  getJob,
  getJobResult,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Folded } from '@/shared/ui/folded';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { dateLabel, formatMoney, formatNumber, formatPercent } from '@/shared/lib/format';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Textarea } from '@/shared/ui/textarea';

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
const num = (value: number | null | undefined, digits = 2) => formatNumber(value, { digits });
const pct = (value: number | null | undefined) => formatPercent(value, { digits: 1, signed: true });

/** Explicit network sync of one company's dataset, as the old Ficha buttons, run by the worker. */
function SyncButton({
  symbol,
  dataset,
  label,
}: {
  symbol: string;
  dataset: 'surprises' | 'estimates' | 'insiders';
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
    if (!synced) return;
    const key = dataset === 'insiders' ? 'insiders' : 'research';
    void queryClient.invalidateQueries({ queryKey: ['market', key, symbol] });
  }, [synced, symbol, dataset, queryClient]);
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
        <HowToRead>
          Consenso de analistas de Yahoo Finance, sin licencia formal. Yahoo no ofrece un histórico
          point-in-time: GABI guarda cada captura con su fecha real, así que el histórico propio
          solo crece hacia delante. No entra en el score sin validación explícita en Investigación.
        </HowToRead>
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

const money = (value: number | null | undefined) => formatMoney(value);

const INSIDER_COLUMNS = [
  'Fecha',
  'Insider',
  'Cargo',
  'Operación',
  'Acciones',
  'Precio',
  '¿Plan 10b5-1?',
];

function InsidersContent({ symbol }: { symbol: string }) {
  const insiders = useQuery({
    queryKey: ['market', 'insiders', symbol],
    queryFn: ({ signal }) => getCompanyInsiders(symbol, signal),
  });
  if (insiders.isPending) return <LoadingState />;
  if (insiders.isError)
    return <ErrorState error={insiders.error} retry={() => void insiders.refetch()} />;
  const data = insiders.data;
  return (
    <>
      <HowToRead>
        Compras y ventas de directivos y consejeros con sus propias acciones. Una compra en mercado
        abierto (código P) fuera de un plan 10b5-1 preprogramado es la señal más informativa; ventas
        y ejercicios de opciones son mucho más rutinarios. Informativo: no entra en el Composite
        Score.
      </HowToRead>
      <SyncButton symbol={symbol} dataset="insiders" label="Actualizar insiders de esta empresa" />
      <dl className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">Compras ({data.months} meses)</dt>
          <dd className="text-lg font-semibold">{data.n_buys}</dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">Ventas ({data.months} meses)</dt>
          <dd className="text-lg font-semibold">{data.n_sells}</dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs text-muted-foreground">Neto comprado − vendido</dt>
          <dd className="text-lg font-semibold">{money(data.net_value)}</dd>
        </div>
      </dl>
      {data.n_buys > 0 && data.has_10b5_1_only_buys && (
        <p className="text-xs" role="alert">
          Todas las compras recientes son de un plan 10b5-1 preprogramado: mucho menos informativas
          que una compra discrecional decidida ahora.
        </p>
      )}
      {data.recent.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" aria-label="Operaciones de insiders">
            <thead>
              <tr className="border-b">
                {INSIDER_COLUMNS.map((title) => (
                  <th key={title} className="py-1.5 pr-3 font-medium">
                    {title}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.recent.map((row, index) => (
                <tr key={index} className="border-b last:border-0">
                  <td className="py-1.5 pr-3">{dateLabel(row.transaction_date)}</td>
                  <td className="py-1.5 pr-3">{row.owner_name ?? '—'}</td>
                  <td className="py-1.5 pr-3">{row.owner_title ?? '—'}</td>
                  <td className="py-1.5 pr-3">{row.transaction_label ?? '—'}</td>
                  <td className="py-1.5 pr-3">{num(row.shares, 0)}</td>
                  <td className="py-1.5 pr-3">{num(row.price_per_share)}</td>
                  <td className="py-1.5 pr-3">
                    {row.is_10b5_1_plan == null ? '—' : row.is_10b5_1_plan ? 'Sí' : 'No'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.recent_total > data.recent.length && (
            <p className="mt-1 text-xs text-muted-foreground">
              Se muestran las {data.recent.length} más recientes de {data.recent_total}.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs">
          Sin operaciones de insiders en los últimos {data.months} meses en la caché para esta
          empresa.
        </p>
      )}
      {data.fetched_at && (
        <p className="text-xs text-muted-foreground">
          Última descarga de Form 4: {dateLabel(data.fetched_at.slice(0, 10))}.
        </p>
      )}
    </>
  );
}

export function Insiders({ symbol }: { symbol: string }) {
  return (
    <Folded title="Actividad de insiders (SEC Form 4, informativo)">
      <InsidersContent symbol={symbol} />
    </Folded>
  );
}

function AnalysisPromptContent({ symbol }: { symbol: string }) {
  const [copied, setCopied] = useState(false);
  const prompt = useQuery({
    queryKey: ['market', 'analysis-prompt', symbol],
    queryFn: ({ signal }) => getAnalysisPrompt(symbol, signal),
  });
  if (prompt.isPending) return <LoadingState />;
  if (prompt.isError)
    return <ErrorState error={prompt.error} retry={() => void prompt.refetch()} />;
  const text = prompt.data.prompt;
  return (
    <>
      <p className="text-xs text-muted-foreground">
        Texto para pegar en el asistente de IA que prefieras, junto con los documentos que le añadas
        (earnings call, guidance, noticias). GABI no llama a ninguna IA. Regla de diseño: la IA
        nunca calcula métricas financieras; los números vienen siempre de GABI.
      </p>
      <Textarea
        readOnly
        aria-label="Prompt para analizar con IA"
        className="h-72 w-full bg-muted/30 font-mono text-xs"
        value={text}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => void navigator.clipboard?.writeText(text).then(() => setCopied(true))}
      >
        {copied ? 'Copiado' : 'Copiar prompt'}
      </Button>
      <p className="text-xs text-muted-foreground">
        Antes de pegarlo, añade el texto de la earnings call, el guidance y las noticias relevantes
        donde el prompt lo indica. Sin eso, la IA solo podrá trabajar con los números y los enlaces
        a los informes oficiales.
      </p>
    </>
  );
}

export function AnalysisPrompt({ symbol }: { symbol: string }) {
  return (
    <Folded title="Prompt para analizar con IA">
      <AnalysisPromptContent symbol={symbol} />
    </Folded>
  );
}
