import { useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileCheck2 } from 'lucide-react';
import type {
  CardCatalyst,
  CardContent,
  CardInvalidation,
  InvestmentCard,
} from '@/shared/api/generated/types.gen';
import { createCard, getCompanyCards, moveCard, saveCard } from '@/shared/api/client';
import { Badge } from '@/shared/ui/badge';
import { Button } from '@/shared/ui/button';
import { Hash } from '@/shared/ui/hash';
import { HowToRead } from '@/shared/ui/how-to-read';
import { Input } from '@/shared/ui/input';
import { NativeSelect } from '@/shared/ui/native-select';
import { ErrorState } from '@/shared/ui/resource-state';
import { Textarea } from '@/shared/ui/textarea';
import { dateLabel, formatNumber, formatPercent } from '@/shared/lib/format';

const SCENARIOS = ['bear', 'base', 'bull'] as const;
const SCENARIO_LABEL = { bear: 'Pesimista', base: 'Base', bull: 'Optimista' } as const;
const STATE_LABEL: Record<InvestmentCard['state'], string> = {
  incompleta: 'Incompleta',
  analizada: 'Analizada',
  publicada: 'Publicada',
  descartada: 'Descartada',
};
const EMPTY_CONDITION: CardInvalidation = {
  description: '',
  metric: '',
  source: '',
  operator: null,
  threshold: null,
  persistence: null,
  review_by: null,
};

type Draft = Required<
  Pick<
    CardContent,
    | 'thesis'
    | 'discrepancy'
    | 'scenarios'
    | 'sensitivity'
    | 'catalysts'
    | 'risks'
    | 'invalidation'
    | 'confidence'
    | 'review_due'
    | 'position_eur'
    | 'notes'
  >
>;

function draftOf(content?: CardContent): Draft {
  const scenario = (name: (typeof SCENARIOS)[number]) => ({
    price: content?.scenarios?.[name]?.price ?? null,
    assumptions: content?.scenarios?.[name]?.assumptions ?? '',
  });
  return {
    thesis: content?.thesis ?? [],
    discrepancy: content?.discrepancy ?? '',
    scenarios: { bear: scenario('bear'), base: scenario('base'), bull: scenario('bull') },
    sensitivity: content?.sensitivity ?? '',
    catalysts: content?.catalysts?.length
      ? content.catalysts
      : [{ description: '', horizon: null }],
    risks: content?.risks ?? [],
    invalidation: content?.invalidation?.length ? content.invalidation : [EMPTY_CONDITION],
    confidence: content?.confidence ?? null,
    review_due: content?.review_due ?? null,
    position_eur: content?.position_eur ?? null,
    notes: content?.notes ?? '',
  };
}

const lines = (text: string) => text.split('\n').map((line) => line.trim());
const number = (text: string) => (text.trim() === '' ? null : Number(text));

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}

function CardForm({
  card,
  busy,
  onSave,
}: {
  card: InvestmentCard;
  busy: boolean;
  onSave: (draft: Draft) => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(card.content));
  const set = (patch: Partial<Draft>) => setDraft((current) => ({ ...current, ...patch }));
  const catalyst = (index: number, patch: Partial<CardCatalyst>) =>
    set({
      catalysts: draft.catalysts.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    });
  const condition = (index: number, patch: Partial<CardInvalidation>) =>
    set({
      invalidation: draft.invalidation.map((item, i) =>
        i === index ? { ...item, ...patch } : item,
      ),
    });
  return (
    <form
      className="mt-4 space-y-4 border-t pt-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(draft);
      }}
    >
      <Field label="Tesis (máximo tres líneas)">
        <Textarea
          rows={3}
          value={draft.thesis.join('\n')}
          onChange={(event) => set({ thesis: lines(event.target.value).slice(0, 3) })}
          className="w-full"
        />
      </Field>
      <Field label="Expectativa discrepante: qué descuenta el precio y por qué discrepas">
        <Textarea
          rows={2}
          value={draft.discrepancy}
          onChange={(event) => set({ discrepancy: event.target.value })}
          className="w-full"
        />
      </Field>
      <fieldset className="space-y-2">
        <legend className="font-medium">
          Valoración por escenarios (precio por acción en USD)
        </legend>
        {SCENARIOS.map((name) => (
          <div key={name} className="grid gap-2 sm:grid-cols-[8rem_10rem_1fr] sm:items-center">
            <span>{SCENARIO_LABEL[name]}</span>
            <Input
              type="number"
              step="any"
              min="0"
              aria-label={'Precio ' + SCENARIO_LABEL[name]}
              value={draft.scenarios[name]?.price ?? ''}
              onChange={(event) =>
                set({
                  scenarios: {
                    ...draft.scenarios,
                    [name]: { ...draft.scenarios[name], price: number(event.target.value) },
                  },
                })
              }
            />
            <Input
              aria-label={'Supuestos ' + SCENARIO_LABEL[name]}
              placeholder="Supuestos"
              value={draft.scenarios[name]?.assumptions ?? ''}
              onChange={(event) =>
                set({
                  scenarios: {
                    ...draft.scenarios,
                    [name]: { ...draft.scenarios[name], assumptions: event.target.value },
                  },
                })
              }
            />
          </div>
        ))}
      </fieldset>
      <Field label="Sensibilidad: qué supuesto mueve más el valor">
        <Textarea
          rows={2}
          value={draft.sensitivity}
          onChange={(event) => set({ sensitivity: event.target.value })}
          className="w-full"
        />
      </Field>
      <fieldset className="space-y-2">
        <legend className="font-medium">Catalizadores con horizonte</legend>
        {draft.catalysts.map((item, index) => (
          <div key={index} className="grid gap-2 sm:grid-cols-[1fr_11rem]">
            <Input
              aria-label="Catalizador"
              value={item.description ?? ''}
              onChange={(event) => catalyst(index, { description: event.target.value })}
            />
            <Input
              type="date"
              aria-label="Horizonte del catalizador"
              value={item.horizon ?? ''}
              onChange={(event) => catalyst(index, { horizon: event.target.value || null })}
            />
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() =>
            set({ catalysts: [...draft.catalysts, { description: '', horizon: null }] })
          }
        >
          Añadir catalizador
        </Button>
      </fieldset>
      <Field label="Riesgos (uno por línea)">
        <Textarea
          rows={3}
          value={draft.risks.join('\n')}
          onChange={(event) => set({ risks: lines(event.target.value) })}
          className="w-full"
        />
      </Field>
      <fieldset className="space-y-2">
        <legend className="font-medium">Condiciones de invalidación medibles</legend>
        {draft.invalidation.map((item, index) => (
          <div key={index} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-2">
            <Input
              aria-label="Condición"
              placeholder="Qué la invalidaría"
              value={item.description ?? ''}
              onChange={(event) => condition(index, { description: event.target.value })}
            />
            <Input
              aria-label="Métrica"
              placeholder="Métrica (p. ej., margen operativo)"
              value={item.metric ?? ''}
              onChange={(event) => condition(index, { metric: event.target.value })}
            />
            <Input
              aria-label="Fuente"
              placeholder="Fuente (p. ej., 10-K)"
              value={item.source ?? ''}
              onChange={(event) => condition(index, { source: event.target.value })}
            />
            <div className="grid grid-cols-[5rem_1fr] gap-2">
              <NativeSelect
                aria-label="Operador"
                value={item.operator ?? ''}
                onChange={(event) =>
                  condition(index, {
                    operator: (event.target.value || null) as CardInvalidation['operator'],
                  })
                }
              >
                <option value="">—</option>
                {['<', '<=', '>', '>='].map((operator) => (
                  <option key={operator}>{operator}</option>
                ))}
              </NativeSelect>
              <Input
                type="number"
                step="any"
                aria-label="Umbral"
                placeholder="Umbral"
                value={item.threshold ?? ''}
                onChange={(event) => condition(index, { threshold: number(event.target.value) })}
              />
            </div>
            <Input
              type="number"
              min="1"
              max="20"
              aria-label="Persistencia"
              placeholder="Periodos seguidos"
              value={item.persistence ?? ''}
              onChange={(event) => condition(index, { persistence: number(event.target.value) })}
            />
            <Input
              type="date"
              aria-label="Revisar la condición el"
              value={item.review_by ?? ''}
              onChange={(event) => condition(index, { review_by: event.target.value || null })}
            />
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => set({ invalidation: [...draft.invalidation, EMPTY_CONDITION] })}
        >
          Añadir condición
        </Button>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Confianza subjetiva (no es una probabilidad)">
          <NativeSelect
            value={draft.confidence ?? ''}
            onChange={(event) =>
              set({ confidence: (event.target.value || null) as Draft['confidence'] })
            }
            className="w-full"
          >
            <option value="">Sin indicar</option>
            <option value="baja">Baja</option>
            <option value="media">Media</option>
            <option value="alta">Alta</option>
          </NativeSelect>
        </Field>
        <Field label="Importe previsto de la posición (€)">
          <Input
            type="number"
            min="1"
            step="any"
            value={draft.position_eur ?? ''}
            onChange={(event) => set({ position_eur: number(event.target.value) })}
          />
        </Field>
        <Field label="Fecha de revisión">
          <Input
            type="date"
            value={draft.review_due ?? ''}
            onChange={(event) => set({ review_due: event.target.value || null })}
          />
        </Field>
      </div>
      <Button type="submit" size="sm" pending={busy}>
        Guardar borrador
      </Button>
    </form>
  );
}

function clean(draft: Draft): CardContent {
  return {
    ...draft,
    thesis: draft.thesis.filter(Boolean),
    risks: draft.risks.filter(Boolean),
    catalysts: draft.catalysts.filter((item) => item.description || item.horizon),
    invalidation: draft.invalidation.filter((item) =>
      Object.values(item).some((value) => value != null && value !== ''),
    ),
  };
}

type Decision = {
  position_eur?: number | null;
  costs?: { buy_eur: number; round_trip_eur: number; round_trip_share: number } | null;
  concentration?: {
    issuer_weight_after: number;
    issuer_cap: number;
    issuer_exceeds: boolean;
    sector: string | null;
    sector_weight_after: number | null;
    sector_cap: number;
    sector_exceeds: boolean;
  } | null;
  passive?: {
    horizon_days: number;
    base_annualised_net: number;
    index_annualised_past: number | null;
    margin_over_index: number | null;
    costs_included: boolean;
    note: string;
  } | null;
};

const euros = (value: number | null | undefined) =>
  value == null ? 'sin dato' : formatNumber(value, { digits: 0 }) + ' €';
const share = (value: number | null | undefined, digits = 1) => formatPercent(value, { digits });

function DecisionContext({ decision }: { decision: Decision }) {
  const { costs, concentration: mix, passive } = decision;
  return (
    <div className="grid gap-2 rounded-lg border p-3 text-xs sm:grid-cols-3">
      <p>
        <span className="block text-muted-foreground">Costes de la posición</span>
        {costs
          ? `${euros(costs.buy_eur)} al comprar · ${euros(costs.round_trip_eur)} ida y vuelta ` +
            `(${share(costs.round_trip_share, 2)} de ${euros(decision.position_eur)})`
          : 'Sin perfil del inversor: costes no calculados'}
      </p>
      <p>
        <span className="block text-muted-foreground">Riesgo de cartera tras añadirla</span>
        {mix
          ? `Emisor ${share(mix.issuer_weight_after)} (límite ${share(mix.issuer_cap, 0)})` +
            (mix.issuer_exceeds ? ' · lo supera' : '') +
            (mix.sector
              ? ` · ${mix.sector} ${share(mix.sector_weight_after)} (límite ${share(mix.sector_cap, 0)})` +
                (mix.sector_exceeds ? ' · lo supera' : '')
              : ' · sector desconocido')
          : 'Sin datos de cartera'}
      </p>
      <p>
        <span className="block text-muted-foreground">Frente a la alternativa pasiva</span>
        {passive
          ? `Base ${formatPercent(passive.base_annualised_net, { digits: 1, signed: true })} anual neto` +
            (passive.costs_included ? '' : ' (sin costes)') +
            ` en ${passive.horizon_days} días · S&P 500 en € ` +
            (passive.index_annualised_past == null
              ? 'sin dato'
              : share(passive.index_annualised_past) + ' anual pasado') +
            (passive.margin_over_index == null
              ? ''
              : ' · margen ' +
                formatPercent(passive.margin_over_index, { digits: 1, signed: true }))
          : 'Sin precio o fecha de revisión'}
      </p>
      {passive && <p className="text-muted-foreground sm:col-span-3">{passive.note}</p>}
    </div>
  );
}

function Published({ card }: { card: InvestmentCard }) {
  const content = draftOf(card.content);
  const snapshot = (card.snapshot ?? {}) as {
    decision?: Decision;
    price?: { value?: number | null; date?: string | null };
    evidence?: { data_coverage?: number | null; statistical_evidence?: string | null } | null;
    absent?: string[];
  };
  return (
    <div className="mt-3 space-y-3">
      <ul className="list-disc pl-5">
        {content.thesis.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p>
        <span className="font-medium">Expectativa discrepante: </span>
        {content.discrepancy}
      </p>
      <table className="w-full text-left">
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="py-1">Escenario</th>
            <th>Precio</th>
            <th>Sobre el precio publicado</th>
            <th>Supuestos</th>
          </tr>
        </thead>
        <tbody>
          {SCENARIOS.map((name) => (
            <tr key={name} className="border-t">
              <td className="py-1">{SCENARIO_LABEL[name]}</td>
              <td className="tabular-nums">
                {formatNumber(content.scenarios[name]?.price, { digits: 2 })}
              </td>
              <td className="tabular-nums">
                {formatPercent(card.scenario_returns[name], { digits: 1, signed: true })}
              </td>
              <td>{content.scenarios[name]?.assumptions}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {content.sensitivity && <p>Sensibilidad: {content.sensitivity}</p>}
      <p>
        Catalizadores:{' '}
        {(card.content.catalysts ?? [])
          .map((item) => `${item.description} (${dateLabel(item.horizon ?? '')})`)
          .join(' · ')}
      </p>
      <p>Riesgos: {content.risks.join(' · ')}</p>
      <ul className="list-disc pl-5">
        {(card.content.invalidation ?? []).map((item, index) => (
          <li key={index}>
            {item.description}: {item.metric} ({item.source}) {item.operator} {item.threshold}{' '}
            durante {item.persistence} periodos · revisar el {dateLabel(item.review_by ?? '')}
          </li>
        ))}
      </ul>
      {snapshot.decision && <DecisionContext decision={snapshot.decision} />}
      <div className="grid gap-2 rounded-lg border p-3 text-xs sm:grid-cols-3">
        <p>
          <span className="block text-muted-foreground">Cobertura del dato</span>
          {formatPercent(snapshot.evidence?.data_coverage, { digits: 0 })}
        </p>
        <p>
          <span className="block text-muted-foreground">Evidencia estadística del modelo</span>
          {snapshot.evidence?.statistical_evidence ?? 'Sin dato'}
        </p>
        <p>
          <span className="block text-muted-foreground">Tu confianza subjetiva</span>
          {content.confidence ?? 'Sin indicar'}
        </p>
        <p className="sm:col-span-3 text-muted-foreground">{card.not_a_probability}</p>
      </div>
      <p className="text-xs text-muted-foreground">
        Publicada el {dateLabel(card.published_at ?? '')} con precio{' '}
        {formatNumber(snapshot.price?.value, { digits: 2 })} USD
        {snapshot.price?.date ? ` del ${dateLabel(snapshot.price.date)}` : ''} · revisión prevista
        el {dateLabel(content.review_due ?? '')}
        {snapshot.absent?.length ? ` · Sin dato al publicar: ${snapshot.absent.join(', ')}` : ''}
        {card.snapshot_sha256 && (
          <>
            {' '}
            · huella <Hash value={card.snapshot_sha256} />
          </>
        )}
      </p>
    </div>
  );
}

/** Investment card (#246): the investor's explicit, versioned decision on this company. */
export function InvestmentCardSection({ symbol }: { symbol: string }) {
  const client = useQueryClient();
  const cards = useQuery({
    queryKey: ['portfolio', 'cards', symbol],
    queryFn: ({ signal }) => getCompanyCards(symbol, signal),
  });
  const [reason, setReason] = useState('');
  const refresh = () => void client.invalidateQueries({ queryKey: ['portfolio', 'cards', symbol] });
  const action = useMutation({
    mutationFn: (run: () => Promise<InvestmentCard>) => run(),
    onSuccess: () => {
      setReason('');
      refresh();
    },
  });
  const items = cards.data?.items ?? [];
  const latest = items[0];
  const editable = latest && (latest.state === 'incompleta' || latest.state === 'analizada');
  return (
    <section aria-labelledby="ficha-titulo" className="mb-6 rounded-xl border bg-card p-5 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="ficha-titulo" className="flex items-center gap-2 text-base font-semibold">
          <FileCheck2 size={18} aria-hidden="true" />
          Ficha de inversión
          {latest && (
            <Badge variant={latest.state === 'publicada' ? 'secondary' : 'outline'}>
              v{latest.version} · {STATE_LABEL[latest.state]}
            </Badge>
          )}
        </h2>
        {(!latest || !editable) && cards.isSuccess && (
          <Button
            size="sm"
            variant="outline"
            pending={action.isPending}
            onClick={() => action.mutate(() => createCard(symbol, latest?.content ?? {}))}
          >
            {latest ? 'Abrir una versión nueva' : 'Empezar la ficha'}
          </Button>
        )}
      </div>
      <HowToRead className="mt-2">
        El ranking solo prioriza qué analizar; la decisión es tuya y queda escrita aquí. Publicar
        exige la ficha completa y guarda los datos de hoy (precio, métricas con su fuente, DCF
        inverso y evidencia) con una huella; una versión publicada no se modifica. Descartarla
        también es una conclusión válida: puede no haber una oportunidad suficientemente defendible.
      </HowToRead>
      {cards.isPending && (
        <p role="status" className="mt-3 text-muted-foreground">
          Consultando la ficha…
        </p>
      )}
      {cards.isError && <ErrorState error={cards.error} retry={() => void cards.refetch()} />}
      {latest?.state === 'publicada' && <Published card={latest} />}
      {latest?.state === 'descartada' && (
        <p className="mt-3">
          Descartada el {dateLabel(latest.discarded_at ?? '')}: {latest.discard_reason}
        </p>
      )}
      {editable && (
        <>
          {latest.missing.length > 0 && (
            <p className="mt-3 text-muted-foreground">
              Para publicar falta {latest.missing.join('; ')}.
            </p>
          )}
          <CardForm
            key={latest.id + ':' + latest.updated_at + ':' + latest.state}
            card={latest}
            busy={action.isPending}
            onSave={(draft) => action.mutate(() => saveCard(latest.id, clean(draft)))}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              pending={action.isPending}
              onClick={() => action.mutate(() => moveCard(latest.id, { target: 'analizada' }))}
            >
              Marcar como analizada
            </Button>
            <Button
              size="sm"
              disabled={latest.missing.length > 0}
              pending={action.isPending}
              onClick={() => action.mutate(() => moveCard(latest.id, { target: 'publicada' }))}
            >
              Publicar
            </Button>
          </div>
        </>
      )}
      {latest && latest.state !== 'descartada' && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
          <Input
            aria-label="Motivo para descartar"
            placeholder="Por qué se descarta"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="max-w-md"
          />
          <Button
            size="sm"
            variant="ghost"
            disabled={!reason.trim()}
            pending={action.isPending}
            onClick={() =>
              action.mutate(() => moveCard(latest.id, { target: 'descartada', reason }))
            }
          >
            Descartar
          </Button>
        </div>
      )}
      {action.isError && (
        <p role="alert" className="mt-2 text-destructive">
          {action.error.message}
        </p>
      )}
      {items.length > 1 && (
        <p className="mt-3 text-xs text-muted-foreground">
          Versiones:{' '}
          {items
            .map(
              (item) =>
                `v${item.version} ${STATE_LABEL[item.state].toLowerCase()} (${dateLabel(item.updated_at)})`,
            )
            .join(' · ')}
        </p>
      )}
    </section>
  );
}
