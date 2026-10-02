import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getLiveForwardReport,
  getLiveLedger,
  getLiveLedgerDecision,
  saveLiveEvaluation,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { JobStatus } from './experiment-jobs';
import { useJob } from '@/shared/api/use-job';
import { formatNumber, formatPercent } from '@/shared/lib/format';

const pct = (value: number | null | undefined) => formatPercent(value, { digits: 2, fixed: true });

function Decision({ seq }: { seq: number }) {
  const query = useQuery({
    queryKey: ['research', 'live-ledger', 'decision', seq],
    queryFn: ({ signal }) => getLiveLedgerDecision(seq, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const { summary, replay, replay_error } = query.data;
  const reproduced =
    replay && replay.fingerprint_matches && replay.scores_match && replay.ranking_matches;
  return (
    <div className="space-y-2 rounded-lg border p-3" role="region" aria-label="Decisión congelada">
      <dl className="grid gap-2 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Fecha de mercado</dt>
          <dd>{summary.market_date ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Registrada</dt>
          <dd>{summary.created_at ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Estado</dt>
          <dd>
            {summary.status ?? '—'}
            {summary.reason ? ` · ${summary.reason}` : ''}
          </dd>
        </div>
        <div className="sm:col-span-3">
          <dt className="text-muted-foreground">Candidatas</dt>
          <dd>{summary.top_n.length ? summary.top_n.join(', ') : 'Ninguna'}</dd>
        </div>
        <div className="sm:col-span-3">
          <dt className="text-muted-foreground">Huella de entradas</dt>
          <dd className="break-all font-mono">{summary.data_fingerprint ?? '—'}</dd>
        </div>
      </dl>
      {replay &&
        (reproduced ? (
          <p className="text-xs text-muted-foreground">
            Entradas, scores y ranking reproducidos desde el registro congelado.
          </p>
        ) : (
          <p className="text-xs text-destructive">
            La reproducción de las entradas guardadas no coincide; revisar el evento.
          </p>
        ))}
      {replay_error && <p className="text-xs text-destructive">{replay_error}</p>}
      <a
        className="text-xs text-primary underline"
        href={'/api/v1/research/live-ledger/decisions/' + String(seq) + '/event.json'}
        download
      >
        Descargar el evento completo
      </a>
    </div>
  );
}

function Report({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();
  const report = useQuery({
    queryKey: ['research', 'live-forward', jobId],
    queryFn: ({ signal }) => getLiveForwardReport(jobId, signal),
  });
  const save = useMutation({
    mutationFn: () => saveLiveEvaluation(jobId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['research', 'live-ledger'] }),
  });
  if (report.isPending) return <LoadingState />;
  if (report.isError)
    return <ErrorState error={report.error} retry={() => void report.refetch()} />;
  const data = report.data;
  return (
    <div className="space-y-3" role="region" aria-label="Informe prospectivo">
      {data.cumulative_return != null ? (
        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border p-3">
            <dt className="text-xs text-muted-foreground">
              Cartera ilustrativa prospectiva · retorno acumulado neto
            </dt>
            <dd className="text-xl font-semibold">{pct(data.cumulative_return)}</dd>
          </div>
          <div className="rounded-lg border p-3">
            <dt className="text-xs text-muted-foreground">SPY · mismo intervalo y coste inicial</dt>
            <dd className="text-xl font-semibold">
              {data.benchmark_return != null ? pct(data.benchmark_return) : 'No disponible'}
            </dd>
          </div>
        </dl>
      ) : (
        <p className="text-muted-foreground">
          Performance aún pendiente o incompleta; no se eliminan empresas sin precio.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Corte {data.as_of}. Primera decisión de cada sesión de entrada, incluso sin señal; apertura
        posterior al registro. Cartera equiponderada con 10 pb/lado sobre lo negociado, separada de
        los backtests y de la prueba ciega.
      </p>
      <div className="overflow-x-auto">
        <table
          className="w-full min-w-[720px] text-left text-xs"
          aria-label="Intervalos prospectivos"
        >
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="py-2">Evento</th>
              <th>Estado</th>
              <th>Entrada</th>
              <th>Fin</th>
              <th>Candidatas</th>
              <th>Sin precio</th>
              <th>Bruto</th>
              <th>Coste</th>
              <th>Neto</th>
              <th>NAV</th>
            </tr>
          </thead>
          <tbody>
            {data.intervals.map((row) => (
              <tr key={row.seq} className="border-b last:border-0">
                <td className="py-1.5">{row.seq}</td>
                <td>{row.status}</td>
                <td>{row.entry}</td>
                <td>
                  {row.end} ({row.end_basis === 'open' ? 'apertura' : 'cierre'})
                </td>
                <td>{row.requested}</td>
                <td>{row.missing.length ? row.missing.join(', ') : '—'}</td>
                <td>{pct(row.gross_return)}</td>
                <td>{pct(row.cost_fraction)}</td>
                <td>{pct(row.net_return)}</td>
                <td>{formatNumber(row.nav, { digits: 4, fixed: true })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
        {data.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-4">
        <a
          className="text-primary underline"
          href={'/api/v1/jobs/' + data.job_id + '/result'}
          download={'gabi-live-forward-' + data.job_id + '.json'}
        >
          Descargar reporte prospectivo
        </a>
        <Button
          variant="outline"
          disabled={save.isPending || save.isSuccess}
          onClick={() => save.mutate()}
        >
          Guardar evaluación como evento nuevo
        </Button>
      </div>
      {save.isError && <ErrorState error={save.error} retry={() => save.reset()} />}
      {save.data && (
        <p role="status">Evaluación #{save.data.seq} añadida; señales originales conservadas.</p>
      )}
    </div>
  );
}

function Performance({ versions }: { versions: string[] }) {
  const [version, setVersion] = useState(versions[0]);
  const state = useJob('live-forward');
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1">
          Versión de modelo del reporte
          <NativeSelect
            value={version}
            onChange={(event) => {
              setVersion(event.target.value);
              state.setJobId(null);
            }}
          >
            {versions.map((item) => (
              <NativeSelectOption key={item} value={item}>
                {item.slice(0, 12)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <Button
          disabled={state.start.isPending}
          onClick={() => {
            state.setJobId(null);
            state.start.mutate({
              kind: 'live_forward_report',
              live_report: { model_version: version },
            });
          }}
        >
          Calcular reporte prospectivo
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        El reporte lee los precios posteriores de la base local en un trabajo explícito; no descarga
        datos ni modifica el registro.
      </p>
      <JobStatus state={state} />
      {state.jobId && state.job.data?.status === 'succeeded' && <Report jobId={state.jobId} />}
    </div>
  );
}

export function LiveLedgerSection() {
  const [selected, setSelected] = useState(0);
  const overview = useQuery({
    queryKey: ['research', 'live-ledger'],
    queryFn: ({ signal }) => getLiveLedger(signal),
  });
  return (
    <details className="rounded-xl border bg-card p-5 text-sm">
      <summary className="cursor-pointer font-medium">
        Registro prospectivo · decisiones congeladas y resultados posteriores
      </summary>
      <div className="mt-3 space-y-3">
        {overview.isPending && <LoadingState />}
        {overview.isError && (
          <ErrorState error={overview.error} retry={() => void overview.refetch()} />
        )}
        {overview.data && !overview.data.integrity.ok && (
          <p className="text-destructive" role="alert">
            Ledger no íntegro: {overview.data.integrity.reason}
          </p>
        )}
        {overview.data?.integrity.ok && overview.data.decisions.length === 0 && (
          <p className="text-muted-foreground">
            Aún no hay decisiones prospectivas. Las registrará la tarea periódica local.
          </p>
        )}
        {overview.data?.integrity.ok && overview.data.decisions.length > 0 && (
          <>
            <p className="text-xs text-muted-foreground">
              Cadena y ancla verificadas · {overview.data.integrity.seq} eventos. LIVE_FORWARD
              describe cuándo se guardó la señal; no acredita validación independiente.
            </p>
            <div className="max-h-80 overflow-auto">
              <table className="w-full text-left text-xs" aria-label="Decisiones registradas">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2">Evento</th>
                    <th>Fase</th>
                    <th>Fecha</th>
                    <th>Estado</th>
                    <th>Candidatas</th>
                    <th>Commit</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.data.decisions.map((row) => (
                    <tr
                      key={row.seq}
                      className={row.seq === selected ? 'border-b bg-muted' : 'border-b'}
                    >
                      <td className="py-1.5">
                        <button
                          type="button"
                          className="text-primary underline"
                          aria-label={`Ver decisión ${row.seq}`}
                          onClick={() => setSelected(row.seq)}
                        >
                          {row.seq}
                        </button>
                      </td>
                      <td>{row.stage}</td>
                      <td>{row.market_date}</td>
                      <td>{row.status}</td>
                      <td>{row.candidates}</td>
                      <td className="font-mono">{row.git_commit ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {selected > 0 && <Decision seq={selected} />}
            {overview.data.live_versions.length === 0 ? (
              <p className="text-muted-foreground">
                Los registros históricos/OOS no se incluyen en la performance LIVE_FORWARD.
              </p>
            ) : (
              <Performance versions={overview.data.live_versions} />
            )}
          </>
        )}
      </div>
    </details>
  );
}
