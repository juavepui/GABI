import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import type { JournalCreate, JournalEntry } from '@/shared/api/generated/types.gen';
import { createJournal, deleteJournal, getJournal, reviewJournal } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { dateLabel } from '@/shared/lib/format';
import { BackLink } from '@/shared/ui/section-links';

const numberOrNull = (value: FormDataEntryValue | null) =>
  value == null || String(value).trim() === '' ? null : Number(value);
const money = (value: number | null | undefined) =>
  value == null ? '—' : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(value);

function Entry({ entry, changed }: { entry: JournalEntry; changed: () => void }) {
  const review = useMutation({
    mutationFn: (body: { review_price: number | null; review_notes: string }) =>
      reviewJournal(entry.id, body),
    onSuccess: changed,
  });
  const remove = useMutation({ mutationFn: () => deleteJournal(entry.id), onSuccess: changed });
  function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    review.mutate({
      review_price: numberOrNull(form.get('review_price')),
      review_notes: String(form.get('review_notes') ?? ''),
    });
  }
  return (
    <article className="rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link
            className="font-semibold text-primary"
            to={'/mercado/empresas/' + encodeURIComponent(entry.symbol)}
          >
            {entry.symbol}
          </Link>
          <span className="ml-2 text-xs text-muted-foreground">{dateLabel(entry.created_at)}</span>
          <p className="mt-1 text-xs text-muted-foreground">
            {entry.horizon || 'Sin horizonte'} · {entry.status}
          </p>
        </div>
        {entry.expected_value && (
          <p className="text-sm">
            Valor esperado {money(entry.expected_value.expected_price)} USD
            <span className="ml-2 text-muted-foreground">
              ({money(entry.expected_value.expected_return_pct)} %)
            </span>
          </p>
        )}
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <p>Entrada: {money(entry.entry_price)} USD</p>
        <p>
          Escenario bajista: {money(entry.bear_price)} USD · {money(entry.bear_prob)} %
        </p>
        <p>
          Escenario base: {money(entry.base_price)} USD · {money(entry.base_prob)} %
        </p>
        <p>
          Escenario alcista: {money(entry.bull_price)} USD · {money(entry.bull_prob)} %
        </p>
        <p>Posición: {money(entry.position_size_pct)} %</p>
      </div>
      <dl className="mt-4 space-y-2 text-sm">
        <div>
          <dt className="font-medium">Tesis</dt>
          <dd className="whitespace-pre-wrap text-muted-foreground">{entry.thesis || '—'}</dd>
        </div>
        <div>
          <dt className="font-medium">Catalizadores</dt>
          <dd className="whitespace-pre-wrap text-muted-foreground">{entry.catalysts || '—'}</dd>
        </div>
        <div>
          <dt className="font-medium">Riesgos</dt>
          <dd className="whitespace-pre-wrap text-muted-foreground">{entry.risks || '—'}</dd>
        </div>
        {entry.notes && (
          <div>
            <dt className="font-medium">Notas</dt>
            <dd className="whitespace-pre-wrap text-muted-foreground">{entry.notes}</dd>
          </div>
        )}
      </dl>
      {entry.status === 'abierta' ? (
        <form
          onSubmit={submitReview}
          className="mt-5 grid gap-3 border-t pt-4 sm:grid-cols-[160px_1fr_auto]"
        >
          <label className="text-xs font-medium">
            Precio revisión (USD)
            <Input className="mt-1" name="review_price" type="number" min={0} step="0.01" />
          </label>
          <label className="text-xs font-medium">
            Aprendizaje
            <Input className="mt-1" name="review_notes" maxLength={5000} />
          </label>
          <Button className="self-end" type="submit" disabled={review.isPending}>
            Marcar revisada
          </Button>
          {review.isError && (
            <p role="alert" className="text-sm text-destructive">
              {review.error.message}
            </p>
          )}
        </form>
      ) : (
        <p className="mt-5 border-t pt-4 text-sm">
          Revisada el {dateLabel(entry.review_date)} · precio {money(entry.review_price)} USD.
          {entry.review_notes && (
            <span className="block text-muted-foreground">{entry.review_notes}</span>
          )}
        </p>
      )}
      <details className="mt-5 text-xs">
        <summary className="cursor-pointer text-muted-foreground">Eliminar entrada</summary>
        <Button
          className="mt-2"
          type="button"
          size="sm"
          variant="destructive"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          Confirmar eliminación
        </Button>
        {remove.isError && (
          <p role="alert" className="mt-2 text-destructive">
            {remove.error.message}
          </p>
        )}
      </details>
    </article>
  );
}

export function JournalPage() {
  const [params] = useSearchParams();
  const prefill = params.get('symbol') ?? '';
  const [offset, setOffset] = useState(0);
  const [onlyOpen, setOnlyOpen] = useState(false);
  const queryClient = useQueryClient();
  const entries = useQuery({
    queryKey: ['portfolio', 'journal', offset, onlyOpen],
    queryFn: ({ signal }) => getJournal(offset, signal, onlyOpen),
  });
  const create = useMutation({
    mutationFn: createJournal,
    onSuccess: () => {
      setOffset(0);
      void queryClient.invalidateQueries({ queryKey: ['portfolio', 'journal'] });
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const form = new FormData(element);
    const body: JournalCreate = {
      symbol: String(form.get('symbol') ?? ''),
      horizon: String(form.get('horizon') ?? ''),
      entry_price: numberOrNull(form.get('entry_price')),
      thesis: String(form.get('thesis') ?? ''),
      bear_price: numberOrNull(form.get('bear_price')),
      base_price: numberOrNull(form.get('base_price')),
      bull_price: numberOrNull(form.get('bull_price')),
      bear_prob: numberOrNull(form.get('bear_prob')),
      base_prob: numberOrNull(form.get('base_prob')),
      bull_prob: numberOrNull(form.get('bull_prob')),
      catalysts: String(form.get('catalysts') ?? ''),
      risks: String(form.get('risks') ?? ''),
      position_size_pct: numberOrNull(form.get('position_size_pct')),
      notes: String(form.get('notes') ?? ''),
    };
    create.mutate(body, { onSuccess: () => element.reset() });
  }
  return (
    <div className="space-y-6">
      <header>
        <BackLink to="/cartera">Cartera objetivo</BackLink>
        <h1 className="mt-3 text-3xl font-semibold">Diario de inversión</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Escribe la tesis antes de invertir y revísala después. Las entradas permanecen en la base
          local de este equipo.
        </p>
      </header>
      <details className="rounded-xl border bg-card p-5" open={Boolean(prefill)}>
        <summary className="cursor-pointer font-semibold">Nueva tesis</summary>
        <form onSubmit={submit} className="mt-5 space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">
              Símbolo
              <Input
                className="mt-1"
                name="symbol"
                required
                maxLength={20}
                defaultValue={prefill}
              />
            </label>
            <label className="text-sm">
              Horizonte
              <select
                name="horizon"
                className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm"
              >
                <option>Medio (6-12 meses)</option>
                <option>Corto (&lt;6 meses)</option>
                <option>Largo (&gt;12 meses)</option>
              </select>
            </label>
            <label className="text-sm">
              Precio entrada (USD)
              <Input className="mt-1" name="entry_price" type="number" min={0} step="0.01" />
            </label>
          </div>
          <label className="block text-sm">
            Tesis
            <textarea
              name="thesis"
              maxLength={5000}
              rows={3}
              className="mt-1 w-full rounded-md border bg-background p-2"
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-3">
            {(['bear', 'base', 'bull'] as const).map((key, index) => (
              <div key={key} className="space-y-3 rounded-lg border p-3">
                <p className="text-sm font-medium">{['Bajista', 'Base', 'Alcista'][index]}</p>
                <label className="block text-xs">
                  Precio USD
                  <Input className="mt-1" name={key + '_price'} type="number" min={0} step="0.01" />
                </label>
                <label className="block text-xs">
                  Probabilidad %
                  <Input
                    className="mt-1"
                    name={key + '_prob'}
                    type="number"
                    min={0}
                    max={100}
                    step="0.1"
                  />
                </label>
              </div>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm">
              Catalizadores
              <Input className="mt-1" name="catalysts" maxLength={5000} />
            </label>
            <label className="text-sm">
              Riesgos
              <Input className="mt-1" name="risks" maxLength={5000} />
            </label>
            <label className="text-sm">
              Tamaño posición %
              <Input
                className="mt-1"
                name="position_size_pct"
                type="number"
                min={0}
                max={100}
                step="0.1"
              />
            </label>
            <label className="text-sm">
              Notas
              <Input className="mt-1" name="notes" maxLength={5000} />
            </label>
          </div>
          <Button type="submit" disabled={create.isPending}>
            Guardar tesis
          </Button>
          {create.isError && (
            <p role="alert" className="text-sm text-destructive">
              {create.error.message}
            </p>
          )}
          {create.isSuccess && (
            <p role="status" className="text-sm">
              Tesis guardada en el diario local.
            </p>
          )}
        </form>
      </details>
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Entradas existentes</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={onlyOpen}
            onChange={(event) => {
              setOnlyOpen(event.target.checked);
              setOffset(0);
            }}
          />
          Mostrar solo entradas abiertas (sin revisar)
        </label>
        {entries.isPending && <LoadingState />}
        {entries.isError && (
          <ErrorState error={entries.error} retry={() => void entries.refetch()} />
        )}
        {entries.data?.items.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {onlyOpen ? 'No hay tesis abiertas.' : 'Todavía no hay tesis.'}
          </p>
        )}
        {entries.data?.items.map((entry) => (
          <Entry
            key={entry.id}
            entry={entry}
            changed={() =>
              void queryClient.invalidateQueries({ queryKey: ['portfolio', 'journal'] })
            }
          />
        ))}
        {entries.data && (
          <div className="flex items-center gap-3 text-sm">
            <Button
              type="button"
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Anterior
            </Button>
            <span>
              {offset + 1}–{Math.min(offset + 50, entries.data.total)} de {entries.data.total}
            </span>
            <Button
              type="button"
              variant="outline"
              disabled={offset + 50 >= entries.data.total}
              onClick={() => setOffset(offset + 50)}
            >
              Siguiente
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
