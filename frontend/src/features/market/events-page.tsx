import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  compareSignals,
  createJob,
  getJob,
  getJobResult,
  getSignals,
  getSnapshotEarnings,
  recordFilingCheck,
} from '@/shared/api/client';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { Badge } from '@/shared/ui/badge';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { SnapshotPicker } from './snapshot-picker';
import { eventText } from './event-text';
import { useSnapshots } from './queries';
import { dateLabel, dateText } from '@/shared/lib/format';
import { PageHeader } from '@/shared/ui/page-header';
import type { SignalEvent } from '@/shared/api/generated/types.gen';

const labels: Record<string, string> = {
  top_n_entry: 'Entra entre las primeras',
  top_n_exit: 'Sale de las primeras',
  score_change: 'Cambio de puntuación',
  rank_change: 'Cambio de puesto',
  confidence_drop: 'Le faltan más datos que antes',
  sector_change: 'Cambio de sector',
  eligibility_change: 'Ya no se puede puntuar',
};
const severities: Record<string, string> = {
  MATERIAL: 'Importante',
  WATCH: 'A vigilar',
  INFO: 'Informativo',
};
const severityOrder: Record<string, number> = { MATERIAL: 0, WATCH: 1, INFO: 2 };

/** One list for the comparison just made and for the saved history: each change in plain words,
 *  with a link to the company's page, where its current position in the ranking is shown.
 *  `basketSize` gives each event the Top-N of the basket it was compared with. */
function EventList({
  items,
  basketSize,
  showDate = true,
}: {
  items: SignalEvent[];
  basketSize: (event: SignalEvent) => number | null;
  showDate?: boolean;
}) {
  return (
    <ul className="mt-4 divide-y">
      {items.map((event, index) => (
        <li key={event.id ?? event.symbol + event.event_type + index} className="py-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={event.severity === 'MATERIAL' ? 'destructive' : 'secondary'}>
              {severities[event.severity] ?? event.severity}
            </Badge>
            <Link
              className="font-medium text-primary"
              to={'/empresas/' + encodeURIComponent(event.symbol)}
            >
              {event.symbol}
            </Link>
            <span>{labels[event.event_type] ?? event.event_type}</span>
            {showDate && event.detected_at && (
              <span className="text-xs text-muted-foreground">{dateLabel(event.detected_at)}</span>
            )}
          </div>
          <p className="mt-1 text-muted-foreground">{eventText(event, basketSize(event))}</p>
        </li>
      ))}
    </ul>
  );
}

type FilingPreview = {
  checked: number;
  with_comparison: number;
  events: Array<{
    symbol: string;
    event_type: string;
    severity: string;
    cause: string;
  }>;
};
function isFilingPreview(value: unknown): value is FilingPreview {
  return Boolean(
    value &&
    typeof value === 'object' &&
    'events' in value &&
    Array.isArray(value.events) &&
    'checked' in value,
  );
}

/** Eventos (#193): what changed since a saved basket (ranking, SEC filings) and the upcoming
 *  earnings of its companies. Data changes, never orders; the Hoy alerts link here. */
export function EventsPage() {
  const queryClient = useQueryClient();
  const snapshots = useSnapshots();
  const [severity, setSeverity] = useState('');
  const [sinceHours, setSinceHours] = useState(24 * 7);
  const signals = useQuery({
    queryKey: ['market', 'signals', severity, sinceHours],
    queryFn: ({ signal }) => getSignals({ severity, sinceHours }, signal),
  });
  const [selected, setSelected] = useState<number | null>(null);
  const [filingJobId, setFilingJobId] = useState<string | null>(null);
  const compare = useMutation({
    mutationFn: compareSignals,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['market', 'signals'] }),
  });
  const activeSnapshot = selected ?? snapshots.data?.items[0]?.id ?? null;
  const earnings = useQuery({
    queryKey: ['market', 'snapshots', activeSnapshot, 'earnings'],
    queryFn: ({ signal }) => getSnapshotEarnings(activeSnapshot!, signal),
    enabled: activeSnapshot != null,
  });
  const filingJob = useQuery({
    queryKey: ['job', filingJobId],
    queryFn: ({ signal }) => getJob(filingJobId!, signal),
    enabled: filingJobId != null,
    refetchInterval: (query) =>
      ['queued', 'running'].includes(query.state.data?.status ?? '') ? 2000 : false,
  });
  const filingResult = useQuery({
    queryKey: ['job-result', filingJobId],
    queryFn: ({ signal }) => getJobResult(filingJobId!, signal),
    enabled: filingJob.data?.status === 'succeeded',
  });
  const checkFilings = useMutation({
    mutationFn: (snapshotId: number) =>
      createJob({
        kind: 'filing_check',
        snapshot_id: snapshotId,
        idempotency_key: 'filing:' + snapshotId + ':' + crypto.randomUUID(),
      }),
    onSuccess: (queued) => setFilingJobId(queued.id),
  });
  const recordFilings = useMutation({
    mutationFn: () => recordFilingCheck(filingJobId!),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['market', 'signals'] }),
  });
  function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    compare.mutate({
      snapshot_id: selected ?? Number(form.get('snapshot_id')),
      rank_change: Number(form.get('rank_change')),
      score_change: Number(form.get('score_change')),
      confidence_drop: Number(form.get('confidence_drop')),
    });
  }
  const options = snapshots.data?.items ?? [];
  const basketSize = (id: number | null | undefined) =>
    options.find((item) => item.id === id)?.candidates ?? null;
  const compared = options.find((item) => item.id === compare.variables?.snapshot_id);
  const comparedItems = [...(compare.data?.items ?? [])].sort(
    (a, b) =>
      (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9) ||
      a.symbol.localeCompare(b.symbol),
  );
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/', label: 'Hoy' }}
        title="Eventos"
        description={
          <>
            Qué ha cambiado en una cartera que guardaste: puestos en el ranking, informes nuevos
            presentados a la SEC y próximas presentaciones de resultados. Son avisos para que
            revises, nunca órdenes de compra o venta.
          </>
        }
      />
      {snapshots.isPending && <LoadingState />}
      {snapshots.isError && (
        <ErrorState error={snapshots.error} retry={() => void snapshots.refetch()} />
      )}
      {options.length > 0 && (
        <form onSubmit={run} className="rounded-xl border bg-card p-5">
          <h2 className="text-lg font-semibold">Comparar con el ranking actual</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SnapshotPicker
              label="Cesta de referencia"
              items={options}
              value={selected ?? options[0].id}
              onChange={(id) => {
                setSelected(id);
                setFilingJobId(null);
              }}
            />
            <label className="text-sm">
              Avisar si cambia de puesto en al menos
              <Input
                className="mt-1"
                name="rank_change"
                type="number"
                min={1}
                defaultValue={5}
                required
              />
            </label>
            <label className="text-sm">
              Avisar si la puntuación cambia al menos
              <Input
                className="mt-1"
                name="score_change"
                type="number"
                min={0.1}
                max={100}
                step={0.1}
                defaultValue={10}
                required
              />
            </label>
            <label className="text-sm">
              Avisar si los datos disponibles bajan al menos
              <Input
                className="mt-1"
                name="confidence_drop"
                type="number"
                min={0.1}
                max={100}
                step={0.1}
                defaultValue={20}
                required
              />
            </label>
          </div>
          <Button className="mt-4" type="submit" pending={compare.isPending}>
            Comparar ahora
          </Button>
          {compare.isError && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {compare.error.message}
            </p>
          )}
          {compare.data && (
            <div className="mt-4">
              <p role="status" className="text-sm">
                {compare.data.items.length === 0
                  ? 'Ningún cambio supera los avisos que has puesto'
                  : `${compare.data.items.length} cambios`}{' '}
                desde que guardaste la cesta
                {compared ? ` «${compared.name}» (${dateText(compared.as_of_date)})` : ''}. Los más
                importantes van primero.
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {compare.data.status === 'EXPERIMENTAL'
                  ? 'Has cambiado los avisos por defecto, así que salen más o menos cambios de lo habitual. '
                  : ''}
                El puesto 1 es la empresa mejor puntuada. Pulsa una empresa para ver su puesto de
                hoy, o mira{' '}
                <Link className="text-primary underline" to="/descubrir">
                  el ranking completo
                </Link>
                .
              </p>
              {comparedItems.length > 0 && (
                <EventList
                  items={comparedItems}
                  basketSize={() => compared?.candidates ?? null}
                  showDate={false}
                />
              )}
            </div>
          )}
        </form>
      )}
      {options.length === 0 && snapshots.isSuccess && (
        <p className="text-sm text-muted-foreground">
          Todavía no has guardado ninguna cartera. En Cartera objetivo, pulsa «Guardar esta cartera
          para seguirla» y aquí verás después qué ha cambiado.
        </p>
      )}
      {activeSnapshot != null && (
        <>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="text-lg font-semibold">Cambios en sus informes oficiales (SEC)</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Compara el último informe anual (10-K) o trimestral (10-Q) de cada empresa con el
              anterior y señala los cambios grandes. Usa los informes ya guardados en tu equipo.
            </p>
            <Button
              className="mt-4"
              type="button"
              variant="outline"
              pending={checkFilings.isPending}
              onClick={() => checkFilings.mutate(activeSnapshot)}
            >
              Comprobar informes
            </Button>
            {checkFilings.isError && (
              <p role="alert" className="mt-2 text-sm text-destructive">
                {checkFilings.error.message}
              </p>
            )}
            {filingJobId && (
              <p role="status" className="mt-3 text-sm">
                Comprobando informes: {filingJob.data?.phase ?? 'en espera'}.
              </p>
            )}
            {filingJob.data?.status === 'failed' && (
              <p className="text-sm text-destructive">
                No se pudo terminar la comparación. Puedes ver el error en Administración →
                Trabajos.
              </p>
            )}
            {filingResult.isError && (
              <ErrorState error={filingResult.error} retry={() => void filingResult.refetch()} />
            )}
            {isFilingPreview(filingResult.data) && (
              <>
                <p className="mt-3 text-sm">
                  {filingResult.data.with_comparison}/{filingResult.data.checked} pares con datos
                  comparables; {filingResult.data.events.length} cambios materiales.
                </p>
                <ul className="mt-3 divide-y">
                  {filingResult.data.events.map((event, index) => (
                    <li key={event.symbol + event.event_type + index} className="py-2 text-sm">
                      <strong>{event.symbol}</strong> · {event.cause}
                    </li>
                  ))}
                </ul>
                <Button
                  type="button"
                  className="mt-3"
                  pending={recordFilings.isPending}
                  disabled={recordFilings.isSuccess}
                  onClick={() => recordFilings.mutate()}
                >
                  Guardar comparación y eventos
                </Button>
                {recordFilings.isSuccess && (
                  <p role="status" className="mt-2 text-sm">
                    Comparación SEC guardada en la base local.
                  </p>
                )}
                {recordFilings.isError && (
                  <p role="alert" className="mt-2 text-sm text-destructive">
                    {recordFilings.error.message}
                  </p>
                )}
              </>
            )}
          </section>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="text-lg font-semibold">Próximas presentaciones de resultados</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Fechas conocidas de las empresas de la cesta; contexto, no señal de compra.
            </p>
            {earnings.isPending && <LoadingState />}
            {earnings.isError && (
              <ErrorState error={earnings.error} retry={() => void earnings.refetch()} />
            )}
            {earnings.data?.items.length === 0 && (
              <p className="mt-3 text-sm">Sin fechas próximas conocidas.</p>
            )}
            <ul className="mt-3 divide-y">
              {earnings.data?.items.map((event) => (
                <li
                  key={event.symbol}
                  className="flex flex-wrap justify-between gap-3 py-2 text-sm"
                >
                  <Link
                    className="text-primary underline"
                    to={'/empresas/' + encodeURIComponent(event.symbol)}
                  >
                    {event.symbol}
                  </Link>
                  <span>
                    {dateText(event.event_date)} · {event.days_until} días ·{' '}
                    {event.is_estimate ? 'Fecha aproximada' : 'Confirmada'}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
      <section className="rounded-xl border bg-card p-5">
        <h2 className="text-lg font-semibold">Eventos recientes</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Todos los cambios de las comparaciones que has hecho, con la fecha en que se detectaron.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-3 text-sm">
          <label className="grid gap-1">
            Importancia
            <NativeSelect value={severity} onChange={(event) => setSeverity(event.target.value)}>
              <NativeSelectOption value="">Todas</NativeSelectOption>
              {Object.entries(severities).map(([value, label]) => (
                <NativeSelectOption key={value} value={value}>
                  {label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
          <label className="grid gap-1">
            En las últimas (horas)
            <Input
              className="w-28"
              type="number"
              min={1}
              max={720}
              value={sinceHours}
              onChange={(event) =>
                setSinceHours(Math.min(Math.max(Number(event.target.value) || 1, 1), 720))
              }
            />
          </label>
        </div>
        {signals.isPending && <LoadingState />}
        {signals.isError && (
          <ErrorState error={signals.error} retry={() => void signals.refetch()} />
        )}
        {signals.data?.items.length === 0 && (
          <p className="mt-3 text-sm text-muted-foreground">
            No ha habido cambios en este periodo.
          </p>
        )}
        {signals.data && signals.data.items.length > 0 && (
          <EventList
            items={signals.data.items}
            basketSize={(event) => basketSize(event.from_snapshot_id)}
          />
        )}
      </section>
    </div>
  );
}
