import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useLocation } from 'react-router-dom';
import { NotebookPen } from 'lucide-react';
import type { JournalEntry } from '@/shared/api/generated/types.gen';
import { createJournal, getCompanyJournal } from '@/shared/api/client';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect } from '@/shared/ui/native-select';
import { Textarea } from '@/shared/ui/textarea';
import { ErrorState } from '@/shared/ui/resource-state';
import { dateLabel, formatNumber } from '@/shared/lib/format';

/** Unfolds the checklist's qualitative criteria and scrolls to them. */
function openQualitative() {
  const target = document.getElementById('criterios-cualitativos');
  if (target instanceof HTMLDetailsElement) target.open = true;
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function Thesis({ entry }: { entry: JournalEntry }) {
  const open = entry.status === 'abierta';
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Badge variant={open ? 'secondary' : 'outline'}>{open ? 'Abierta' : 'Revisada'}</Badge>
        <span>Escrita el {dateLabel(entry.created_at)}</span>
        {open && entry.review_due && <span>· revisar el {dateLabel(entry.review_due)}</span>}
        {!open && entry.review_date && <span>· revisada el {dateLabel(entry.review_date)}</span>}
        {entry.entry_price != null && (
          <span>· precio {formatNumber(entry.entry_price, { digits: 2 })} USD</span>
        )}
        {entry.entry_score != null && (
          <span>· score {formatNumber(entry.entry_score, { digits: 1, fixed: true })}</span>
        )}
      </div>
      <p className="mt-1 whitespace-pre-wrap text-sm">{entry.thesis || 'Sin texto de tesis.'}</p>
      {entry.invalidation && (
        <p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">
          La invalidaría: {entry.invalidation}
        </p>
      )}
    </li>
  );
}

/** «Tus tesis sobre APA» (#186): this company's theses and a short template to write one. The price,
 *  the frozen score and the checklist of today are captured by the backend when it is saved. */
export function CompanyTheses({ symbol }: { symbol: string }) {
  const client = useQueryClient();
  const [writing, setWriting] = useState(false);
  const theses = useQuery({
    queryKey: ['portfolio', 'journal', 'company', symbol],
    queryFn: ({ signal }) => getCompanyJournal(symbol, signal),
  });
  const create = useMutation({
    mutationFn: createJournal,
    onSuccess: () => {
      setWriting(false);
      void client.invalidateQueries({ queryKey: ['portfolio', 'journal'] });
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const due = String(form.get('review_due') ?? '');
    create.mutate({
      symbol,
      thesis: String(form.get('thesis') ?? ''),
      invalidation: String(form.get('invalidation') ?? ''),
      horizon: String(form.get('horizon') ?? ''),
      review_due: due || null,
    });
  }
  const { hash } = useLocation();
  // «Sin tesis · escribir una» in the portfolios links here: the page loads first, then it scrolls.
  useEffect(() => {
    if (hash === '#tesis' && theses.isSuccess)
      document.getElementById('tesis')?.scrollIntoView({ block: 'start' });
  }, [hash, theses.isSuccess]);
  const items = theses.data?.items ?? [];
  return (
    <section aria-labelledby="tesis-titulo" className="mb-6 rounded-xl border bg-card p-5 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="tesis-titulo" className="flex items-center gap-2 text-base font-semibold">
          <NotebookPen size={18} aria-hidden="true" />
          Tus tesis sobre {symbol}
        </h2>
        {!writing && (
          <Button size="sm" variant="outline" onClick={() => setWriting(true)}>
            Escribir una tesis
          </Button>
        )}
      </div>
      {/* One line, not the large skeleton: the section must not shrink once loaded (it would move the
          page above a hovered hint and close it). */}
      {theses.isPending && (
        <p role="status" className="mt-3 text-muted-foreground">
          Consultando tus tesis…
        </p>
      )}
      {theses.isError && <ErrorState error={theses.error} retry={() => void theses.refetch()} />}
      {theses.isSuccess && items.length === 0 && !writing && (
        <p className="mt-3 text-muted-foreground">
          Aún no has escrito ninguna. Escribir por qué la comprarías, y qué te haría cambiar de
          opinión, antes de invertir ayuda a revisarla después.
        </p>
      )}
      {items.length > 0 && (
        <ul className="mt-2 divide-y">
          {items.map((entry) => (
            <Thesis key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
      {(theses.data?.total ?? 0) > items.length && (
        <p className="mt-2 text-xs text-muted-foreground">
          Se muestran las {items.length} más recientes.
        </p>
      )}
      {writing && (
        <form onSubmit={submit} className="mt-4 space-y-3 border-t pt-4">
          <label className="block">
            Por qué merece su precio
            <Textarea name="thesis" required maxLength={5000} rows={3} className="mt-1 w-full" />
          </label>
          <label className="block">
            Qué la invalidaría
            <Textarea name="invalidation" maxLength={5000} rows={2} className="mt-1 w-full" />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              Horizonte
              <NativeSelect name="horizon" className="mt-1 w-full">
                <option>Medio (6-12 meses)</option>
                <option>Corto (&lt;6 meses)</option>
                <option>Largo (&gt;12 meses)</option>
              </NativeSelect>
            </label>
            <label>
              Fecha de revisión
              <Input className="mt-1" name="review_due" type="date" />
            </label>
          </div>
          <p className="text-xs text-muted-foreground">
            Al guardarla se anotan el último precio de la caché, el score del modelo congelado y el
            resultado del checklist de hoy, para ver al revisarla qué ha cambiado. Sin fecha, se
            revisa al terminar el horizonte. Antes de escribirla, repasa los{' '}
            <a
              href="#criterios-cualitativos"
              className="text-primary underline"
              onClick={(event) => {
                event.preventDefault();
                openQualitative();
              }}
            >
              criterios cualitativos del checklist
            </a>
            .
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" pending={create.isPending}>
              Guardar tesis
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setWriting(false)}>
              Cancelar
            </Button>
          </div>
          {create.isError && (
            <p role="alert" className="text-destructive">
              {create.error.message}
            </p>
          )}
        </form>
      )}
      <p className="mt-3 text-xs">
        <Link
          className="text-primary underline"
          to={'/cartera/diario?symbol=' + encodeURIComponent(symbol)}
        >
          Ver todas en el diario y revisarlas →
        </Link>
      </p>
    </section>
  );
}
