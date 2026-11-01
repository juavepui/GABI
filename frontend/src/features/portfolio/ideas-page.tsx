import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { Idea, IdeaDetail, IdeaEventCreate } from '@/shared/api/generated/types.gen';
import { addIdeaEvent, addIdeaNote, deleteIdeaNote, getIdea, getIdeas } from '@/shared/api/client';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Input } from '@/shared/ui/input';
import { NativeSelect } from '@/shared/ui/native-select';
import { PageHeader } from '@/shared/ui/page-header';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { dateLabel, formatPercent } from '@/shared/lib/format';

const STATUS: Record<Idea['state']['status'], string> = {
  abierta: 'Abierta',
  cerrada: 'Cerrada',
  retirada: 'Retirada',
};
const EVENT: Record<string, string> = {
  publicada: 'Publicada',
  revisada: 'Revisión',
  retirada: 'Retirada',
  cerrada: 'Cierre',
  corregida: 'Corrección',
};
const pct = (value: number | null | undefined) => formatPercent(value, { digits: 1, signed: true });

function eventText(event: IdeaDetail['events'][number]) {
  const body = event.payload as Record<string, unknown>;
  if (event.kind === 'publicada') return `ficha ${String(body.card_id)}`;
  if (event.kind === 'cerrada')
    return `tesis ${String(body.outcome)} · ${String(body.cause)}${body.executed ? ' · invertida' : ' · no invertida'}`;
  if (event.kind === 'retirada') return String(body.reason);
  if (event.kind === 'corregida')
    return `corrige el evento ${String(body.corrects)}: ${String(body.text)}`;
  return String(body.text ?? '');
}

function Actions({ idea, onDone }: { idea: IdeaDetail; onDone: () => void }) {
  const [kind, setKind] = useState<IdeaEventCreate['kind']>('revisada');
  const [text, setText] = useState('');
  const [outcome, setOutcome] = useState<'acertada' | 'parcial' | 'fallida'>('acertada');
  const [executed, setExecuted] = useState(false);
  const [corrects, setCorrects] = useState(1);
  const [note, setNote] = useState('');
  const event = useMutation({
    mutationFn: (body: IdeaEventCreate) => addIdeaEvent(idea.idea_id, body),
    onSuccess: () => {
      setText('');
      onDone();
    },
  });
  const notes = useMutation({
    mutationFn: (run: () => Promise<IdeaDetail>) => run(),
    onSuccess: () => {
      setNote('');
      onDone();
    },
  });
  const open = idea.state.status === 'abierta';
  const kinds = open
    ? (['revisada', 'cerrada', 'retirada', 'corregida'] as const)
    : (['corregida'] as const);
  return (
    <div className="mt-3 space-y-3 border-t pt-3">
      <div className="flex flex-wrap items-end gap-2">
        <NativeSelect
          aria-label="Tipo de evento"
          value={kinds.includes(kind as never) ? kind : 'corregida'}
          onChange={(change) => setKind(change.target.value as IdeaEventCreate['kind'])}
        >
          {kinds.map((name) => (
            <option key={name} value={name}>
              {EVENT[name]}
            </option>
          ))}
        </NativeSelect>
        {kind === 'cerrada' && open && (
          <>
            <NativeSelect
              aria-label="Resultado de la tesis"
              value={outcome}
              onChange={(change) => setOutcome(change.target.value as typeof outcome)}
            >
              <option value="acertada">Tesis acertada</option>
              <option value="parcial">Parcial</option>
              <option value="fallida">Fallida</option>
            </NativeSelect>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={executed} onChange={() => setExecuted(!executed)} />
              Llegué a invertir
            </label>
          </>
        )}
        {(kind === 'corregida' || !open) && (
          <Input
            type="number"
            min={1}
            max={idea.events.length}
            aria-label="Evento que se corrige"
            value={corrects}
            onChange={(change) => setCorrects(Number(change.target.value))}
            className="w-24"
          />
        )}
        <Input
          aria-label="Texto del evento"
          placeholder={
            kind === 'cerrada'
              ? 'Causa del resultado'
              : kind === 'retirada'
                ? 'Por qué se retira'
                : 'Texto'
          }
          value={text}
          onChange={(change) => setText(change.target.value)}
          className="min-w-64 flex-1"
        />
        <Button
          size="sm"
          disabled={!text.trim()}
          pending={event.isPending}
          onClick={() => {
            const chosen = open ? kind : 'corregida';
            event.mutate({
              kind: chosen,
              text,
              reason: text,
              cause: text,
              outcome: chosen === 'cerrada' ? outcome : null,
              executed,
              corrects: chosen === 'corregida' ? corrects : null,
            });
          }}
        >
          Añadir evento
        </Button>
      </div>
      {event.isError && (
        <p role="alert" className="text-destructive">
          {event.error.message}
        </p>
      )}
      <div className="space-y-1">
        <p className="text-xs font-medium">
          Notas privadas (editables; no forman parte del historial)
        </p>
        {idea.notes.map((item) => (
          <p key={item.id} className="flex items-start justify-between gap-2 text-xs">
            <span className="whitespace-pre-wrap">{item.text}</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => notes.mutate(() => deleteIdeaNote(idea.idea_id, item.id))}
            >
              Borrar
            </Button>
          </p>
        ))}
        <div className="flex gap-2">
          <Input
            aria-label="Nueva nota privada"
            value={note}
            onChange={(change) => setNote(change.target.value)}
            className="flex-1"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!note.trim()}
            pending={notes.isPending}
            onClick={() => notes.mutate(() => addIdeaNote(idea.idea_id, note))}
          >
            Añadir nota
          </Button>
        </div>
      </div>
    </div>
  );
}

function IdeaRow({ idea }: { idea: Idea }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const detail = useQuery({
    queryKey: ['portfolio', 'ideas', idea.idea_id],
    queryFn: ({ signal }) => getIdea(idea.idea_id, signal),
    enabled: open,
  });
  const evaluation = idea.evaluation;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          className="font-medium text-primary underline"
          to={'/empresas/' + encodeURIComponent(idea.symbol) + '#ficha-inversion'}
        >
          {idea.symbol}
        </Link>
        <Badge variant={idea.state.status === 'abierta' ? 'secondary' : 'outline'}>
          {STATUS[idea.state.status]}
        </Badge>
        <span className="text-xs text-muted-foreground">
          Publicada el {dateLabel(idea.state.published_on)}
          {idea.state.ended_on && ` · terminó el ${dateLabel(idea.state.ended_on)}`}
          {idea.state.outcome && ` · tesis ${String(idea.state.outcome.outcome)}`}
        </span>
        {!idea.chain_ok && <Badge variant="destructive">Historial alterado</Badge>}
      </div>
      <p className="mt-1 text-sm tabular-nums">
        {evaluation.status === 'ok'
          ? `${pct(evaluation.return_net)} neto · S&P 500 ${pct(evaluation.index_return)} · diferencia ${pct(evaluation.excess)} · máx. caída ${pct(evaluation.max_drawdown)} · ${evaluation.days} días`
          : `Sin precios suficientes en caché (${(evaluation.missing ?? []).join(', ') || 'menos de dos sesiones'})`}
      </p>
      <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>
        {open ? 'Ocultar historial' : 'Ver historial y notas'}
      </Button>
      {open && detail.isError && (
        <ErrorState error={detail.error} retry={() => void detail.refetch()} />
      )}
      {open && detail.data && (
        <>
          <ol className="mt-2 space-y-1 text-xs">
            {detail.data.events.map((event) => (
              <li key={event.sequence}>
                <span className="font-medium">
                  {event.sequence}. {EVENT[event.kind] ?? event.kind}
                </span>{' '}
                · {dateLabel(event.recorded_at.slice(0, 10))} · {eventText(event)}
              </li>
            ))}
          </ol>
          <Actions
            idea={detail.data}
            onDone={() => void client.invalidateQueries({ queryKey: ['portfolio', 'ideas'] })}
          />
        </>
      )}
    </li>
  );
}

/** History of published ideas (#247): every idea, its additive events and its result against the S&P 500. */
export function IdeasPage() {
  const ideas = useQuery({
    queryKey: ['portfolio', 'ideas'],
    queryFn: ({ signal }) => getIdeas(signal),
  });
  const summary = ideas.data?.summary;
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/cartera', label: 'Cartera objetivo' }}
        title="Historial de ideas"
        description="Cada ficha de inversión publicada, lo que pasó después y su resultado frente al S&P 500 en euros."
      />
      <HowToRead>
        Las revisiones, retiradas, cierres y correcciones se añaden al historial; nada se reescribe
        ni se borra. Cuentan todas las ideas, también las perdedoras, las retiradas y las que no
        llegaste a invertir: mirar solo las ganadoras engaña. Cada idea se mide desde el día en que
        se publicó, neta de los costes de su ficha, frente al S&P 500 en euros en las mismas fechas.
      </HowToRead>
      {ideas.isPending && <LoadingState />}
      {ideas.isError && <ErrorState error={ideas.error} retry={() => void ideas.refetch()} />}
      {summary && (
        <p className="text-sm">
          {summary.ideas} ideas ({summary.open} abiertas, {summary.closed} cerradas,{' '}
          {summary.retired} retiradas) · {summary.beat_index} de {summary.evaluated} evaluadas
          superan al índice · diferencia mediana {pct(summary.median_excess)} · tesis acertadas{' '}
          {summary.thesis_hits.acertada ?? 0}, parciales {summary.thesis_hits.parcial ?? 0},
          fallidas {summary.thesis_hits.fallida ?? 0}
        </p>
      )}
      {ideas.data && ideas.data.items.length === 0 && (
        <p className="text-muted-foreground">
          Aún no hay ideas: se crean al publicar una ficha de inversión en la página de una empresa.
        </p>
      )}
      {ideas.data && ideas.data.items.length > 0 && (
        <ul className="divide-y rounded-xl border bg-card px-5">
          {ideas.data.items.map((idea) => (
            <IdeaRow key={idea.idea_id} idea={idea} />
          ))}
        </ul>
      )}
    </div>
  );
}
