import { lazy, Suspense, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getSnapshotProgress, renameSnapshot } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

const SnapshotCurve = lazy(() => import('./snapshot-curve'));
const pct = (value: number | null | undefined) =>
  value == null
    ? '—'
    : new Intl.NumberFormat('es-ES', {
        maximumFractionDigits: 1,
        minimumFractionDigits: 1,
        signDisplay: 'always',
      }).format(value * 100) + ' %';
const price = (value: number | null | undefined) =>
  value == null ? '—' : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(value);

function Rename({ id, name }: { id: number; name: string }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(name);
  const rename = useMutation({
    mutationFn: () => renameSnapshot(id, value),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['market', 'snapshots'] }),
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    rename.mutate();
  }
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={submit} aria-label="Cambiar nombre">
      <label className="grid gap-1 text-sm">
        Cambiar nombre de este ranking
        <Input value={value} maxLength={80} onChange={(event) => setValue(event.target.value)} />
      </label>
      <Button type="submit" variant="outline" disabled={rename.isPending || !value.trim()}>
        Guardar nombre
      </Button>
      {rename.isError && <ErrorState error={rename.error} retry={() => rename.reset()} />}
      {rename.data && <span role="status">Nombre guardado.</span>}
    </form>
  );
}

/** Progress of a saved ranking from its date until today: equal weights, exactly its candidates. */
export function SnapshotProgress({ id }: { id: number }) {
  const query = useQuery({
    queryKey: ['market', 'snapshots', id, 'progress'],
    queryFn: ({ signal }) => getSnapshotProgress(id, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  return (
    <section
      className="space-y-4 rounded-xl border bg-card p-5 text-sm"
      aria-label="Seguimiento del ranking guardado"
    >
      <div>
        <h2 className="text-lg font-semibold">
          Progreso desde {data.as_of_date} hasta hoy · {data.name}
        </h2>
        <p className="text-xs text-muted-foreground">
          Guardado el {data.created_at.replace('T', ' a las ')} · {data.candidates} candidatas
        </p>
      </div>
      <Rename key={data.name} id={data.id} name={data.name} />
      {data.stale && (
        <p role="status" className="text-muted-foreground">
          {data.data_as_of
            ? `Los precios en caché solo llegan hasta el ${data.data_as_of}, la misma fecha (o anterior) en que se guardó este ranking: todavía no hay ningún día nuevo que comparar. Actualiza los datos en Administración.`
            : 'Todavía no hay ningún precio cacheado para estas empresas. Actualiza los datos en Administración.'}
        </p>
      )}
      {data.portfolio_return == null ? (
        <p className="text-muted-foreground">
          Sin precios suficientes todavía para calcular el progreso de este ranking.
        </p>
      ) : (
        <>
          <dl className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border p-3">
              <dt className="text-xs text-muted-foreground">Cesta guardada (1/N)</dt>
              <dd className="text-xl font-semibold">{pct(data.portfolio_return)}</dd>
            </div>
            <div className="rounded-lg border p-3">
              <dt className="text-xs text-muted-foreground">SPY (mismo periodo)</dt>
              <dd className="text-xl font-semibold">{pct(data.benchmark_return)}</dd>
            </div>
            <div className="rounded-lg border p-3">
              <dt className="text-xs text-muted-foreground">Diferencia</dt>
              <dd className="text-xl font-semibold">{pct(data.excess_return)}</dd>
            </div>
          </dl>
          {data.available < data.requested && (
            <p className="text-xs text-muted-foreground">
              Cobertura {data.available}/{data.requested}; sin precio hasta hoy para{' '}
              {data.missing.join(', ')}. No cuentan como 0 %: se excluyen de la media.
            </p>
          )}
          {data.curve.length > 0 && (
            <Suspense fallback={<p>Preparando gráfico…</p>}>
              <SnapshotCurve points={data.curve} />
            </Suspense>
          )}
          <table className="w-full text-left text-xs" aria-label="Detalle por empresa">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2">Ticker</th>
                <th>Precio {data.as_of_date}</th>
                <th>Precio hoy</th>
                <th>Retorno</th>
              </tr>
            </thead>
            <tbody>
              {data.detail.map((row) => (
                <tr key={row.symbol} className="border-b last:border-0">
                  <td className="py-1">{row.symbol}</td>
                  <td>{price(row.price_start)}</td>
                  <td>{price(row.price_now)}</td>
                  <td>{pct(row.return)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer font-medium">
          A plazo fijo (6 y 12 meses desde que se guardó)
        </summary>
        <ul className="mt-2 space-y-1">
          {data.horizons.map((horizon) => (
            <li key={horizon.months}>
              {horizon.status === 'pending'
                ? `${horizon.months} meses: pendiente hasta ${horizon.end_date}`
                : `${horizon.months} meses: candidatas ${pct(horizon.portfolio_return)} · SPY ${pct(horizon.benchmark_return)} · cobertura ${horizon.available}/${horizon.requested}`}
              {horizon.status === 'incomplete' && (
                <span className="block text-xs text-muted-foreground">
                  Resultado parcial: faltan precios para {(horizon.missing ?? []).join(', ')}.
                </span>
              )}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
