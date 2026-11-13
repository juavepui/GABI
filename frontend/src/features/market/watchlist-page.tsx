import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { ChecklistSummary, WatchlistRow } from '@/shared/api/generated/types.gen';
import {
  getWatchlist,
  getWatchlistChecklists,
  unfollowCompany,
  updateWatchlistNote,
} from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { DataTable } from '@/shared/ui/data-table';
import { Direction } from '@/shared/ui/status';
import { ScoreBar } from '@/shared/ui/score-bar';
import { PageHeader } from '@/shared/ui/page-header';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { dateText, formatNumber } from '@/shared/lib/format';

// The direction in a neutral colour with arrow and word (#320); the level keeps its own reading.
const WORDS = {
  puntos: { up: 'sube', down: 'baja', flat: 'igual' },
  puestos: { up: 'gana', down: 'pierde', flat: 'mismo puesto' },
} as const;

function Change({ value, unit }: { value: number | null | undefined; unit: string }) {
  if (value == null) return null;
  const points = unit === 'puntos';
  return (
    <Direction
      value={value}
      words={points ? WORDS.puntos : WORDS.puestos}
      className="block text-xs"
    >
      {value === 0 ? null : formatNumber(Math.abs(value), { digits: points ? 1 : 0 }) + ' ' + unit}
    </Direction>
  );
}

function Checklist({ summary, pending }: { summary?: ChecklistSummary | null; pending: boolean }) {
  if (pending) return <span className="text-xs text-muted-foreground">Calculando…</span>;
  if (!summary || !summary.evaluated) return <>—</>;
  return (
    <span title={`${summary.evaluated} de ${summary.applicable} criterios con dato`}>
      {summary.passed} / {summary.evaluated}
    </span>
  );
}

function Note({ row }: { row: WatchlistRow }) {
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const save = useMutation({
    mutationFn: (note: string) => updateWatchlistNote(row.symbol, note),
    onSuccess: () => {
      setEditing(false);
      void client.invalidateQueries({ queryKey: ['market', 'watchlist'] });
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(String(new FormData(event.currentTarget).get('note') ?? ''));
  }
  if (!editing)
    return (
      <span className="flex items-start gap-2">
        <span className={row.note ? '' : 'text-muted-foreground'}>{row.note ?? 'Sin nota'}</span>
        <Button
          size="xs"
          variant="ghost"
          aria-label={'Editar la nota de ' + row.symbol}
          onClick={() => setEditing(true)}
        >
          Editar
        </Button>
      </span>
    );
  return (
    <form className="flex flex-col gap-2" onSubmit={submit}>
      <Input
        name="note"
        aria-label={'Nota de ' + row.symbol}
        defaultValue={row.note ?? ''}
        maxLength={500}
        autoFocus
      />
      <span className="flex gap-2">
        <Button size="xs" type="submit" pending={save.isPending}>
          Guardar
        </Button>
        <Button size="xs" type="button" variant="ghost" onClick={() => setEditing(false)}>
          Cancelar
        </Button>
      </span>
      {save.isError && (
        <span role="alert" className="text-xs text-destructive">
          {save.error.message}
        </span>
      )}
    </form>
  );
}

function Remove({ symbol }: { symbol: string }) {
  const client = useQueryClient();
  const remove = useMutation({
    mutationFn: () => unfollowCompany(symbol),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['market', 'watchlist'] }),
  });
  return (
    <>
      <Button
        size="xs"
        variant="ghost"
        pending={remove.isPending}
        aria-label={'Dejar de seguir ' + symbol}
        onClick={() => remove.mutate()}
      >
        Quitar
      </Button>
      {remove.isError && (
        <span role="alert" className="block text-xs text-destructive">
          {remove.error.message}
        </span>
      )}
    </>
  );
}

/** Empresas seguidas (#182): companies the investor marked, read from the cache in one batch. The
 *  checklist is computed per company, so it arrives in a second, separate query. */
export function WatchlistPage() {
  const list = useQuery({
    queryKey: ['market', 'watchlist', 'summary'],
    queryFn: ({ signal }) => getWatchlist(signal),
  });
  const items = list.data?.items ?? [];
  const checklists = useQuery({
    queryKey: ['market', 'watchlist', 'checklist'],
    queryFn: ({ signal }) => getWatchlistChecklists(signal),
    enabled: items.length > 0,
  });
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/descubrir', label: 'Ranking' }}
        title="Empresas seguidas"
        description={
          <>
            Las empresas que marcaste con la estrella «Seguir»: su puntuación y su puesto de hoy, y
            cuánto han cambiado desde que empezaste a seguirlas.
          </>
        }
      />
      {list.isPending && <LoadingState />}
      {list.isError && <ErrorState error={list.error} retry={() => void list.refetch()} />}
      {list.isSuccess && items.length === 0 && (
        <p className="rounded-xl border bg-card p-5 text-sm">
          Aún no sigues ninguna empresa. Pulsa «Seguir» en la{' '}
          <Link className="text-primary underline" to="/descubrir">
            fila del Ranking
          </Link>
          , en la ficha de una empresa o en Comparar.
        </p>
      )}
      {list.data && items.length > 0 && (
        <section className="rounded-xl border bg-card">
          {!list.data.ranking_ready && (
            <p role="status" className="border-b p-4 text-sm text-muted-foreground">
              Todavía no se ha calculado el ranking, así que solo se ven la lista y tus notas.
            </p>
          )}
          {checklists.isError && (
            <p role="status" className="border-b p-4 text-sm text-muted-foreground">
              No se ha podido calcular el checklist: {checklists.error.message}
            </p>
          )}
          <DataTable label="Empresas seguidas">
            <table className="w-full min-w-[900px] text-left text-sm">
              <caption className="sr-only">
                Empresas seguidas, en el orden en que las añadiste. Los cambios cuentan desde ese
                día.
              </caption>
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="p-3 pl-5">
                    Empresa
                  </th>
                  <th scope="col" className="num p-3">
                    Puntuación
                  </th>
                  <th scope="col" className="num p-3">
                    Puesto
                  </th>
                  <th scope="col" className="num p-3">
                    Lista de comprobación
                  </th>
                  <th scope="col" className="p-3">
                    Próximos resultados
                  </th>
                  <th scope="col" className="p-3">
                    Tus notas
                  </th>
                  <th scope="col" className="p-3">
                    Nota
                  </th>
                  <th scope="col" className="p-3">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.symbol} className="border-t align-top">
                    <th scope="row" className="p-3 pl-5 font-normal">
                      <Link
                        className="font-semibold text-primary"
                        to={'/empresas/' + encodeURIComponent(row.symbol)}
                      >
                        {row.symbol}
                      </Link>
                      <span className="block">{row.name ?? 'Nombre no disponible'}</span>
                      <span className="block text-xs text-muted-foreground">
                        Desde el {dateText(row.added_at)}
                        {!row.in_ranking && ' · fuera del ranking actual'}
                      </span>
                    </th>
                    <td className="num p-3">
                      <span className="inline-flex items-center gap-2">
                        <ScoreBar value={row.composite_score} />
                        {formatNumber(row.composite_score, { digits: 1, fixed: true })}
                      </span>
                      <Change value={row.score_change} unit="puntos" />
                    </td>
                    <td className="num p-3">
                      {row.rank == null ? '—' : '#' + row.rank}
                      <Change
                        value={row.rank_change}
                        unit={Math.abs(row.rank_change ?? 0) === 1 ? 'puesto' : 'puestos'}
                      />
                      {!row.same_model && row.score_at_add != null && (
                        <span className="block text-xs text-muted-foreground">
                          Añadida con otra versión del modelo
                        </span>
                      )}
                    </td>
                    <td className="num p-3">
                      <Checklist
                        summary={checklists.data?.items[row.symbol]}
                        pending={checklists.isPending}
                      />
                    </td>
                    <td className="p-3">
                      {row.next_earnings_date ? (
                        <>
                          {dateText(row.next_earnings_date)}
                          {row.next_earnings_is_estimate && (
                            <span className="block text-xs text-muted-foreground">Aproximada</span>
                          )}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="p-3">
                      <Link
                        className="text-primary underline"
                        to={'/cartera/diario?symbol=' + encodeURIComponent(row.symbol)}
                      >
                        {row.open_theses
                          ? row.open_theses === 1
                            ? '1 tesis abierta'
                            : `${row.open_theses} tesis abiertas`
                          : row.theses
                            ? 'Notas cerradas'
                            : 'Escribir por qué la compraría'}
                      </Link>
                    </td>
                    <td className="max-w-72 p-3">
                      <Note row={row} />
                    </td>
                    <td className="p-3">
                      <Remove symbol={row.symbol} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataTable>
          <p className="border-t px-5 py-3 text-xs text-muted-foreground">
            Lista de comprobación: cuántos criterios cumple de los que se pueden comprobar con los
            datos guardados. El cambio de puntuación y de puesto solo aparece si la empresa se
            añadió con la misma versión del modelo (si no, no serían comparables).
          </p>
        </section>
      )}
    </div>
  );
}
