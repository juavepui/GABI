import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { breakBlindSeal, createBlindValidation, getBlindValidations } from '@/shared/api/client';
import type { BlindCreateRequest, BlindStatus } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';
import { BlindActions } from './blind-actions';
import { PageHeader } from '@/shared/ui/page-header';

const today = () => new Date().toISOString().slice(0, 10);

function initialForm(): BlindCreateRequest {
  return {
    name: 'Hipótesis congelada — prueba prospectiva',
    weights_pct: { value: 30, quality: 35, momentum: 25, risk: 10 },
    n_positions: 20,
    rebalance_months: 3,
    start_date: today(),
    unlock_date: '2027-09-17',
  };
}

function CreateValidation() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<BlindCreateRequest>(initialForm);
  const create = useMutation({
    mutationFn: () => createBlindValidation(form),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['research', 'blind-validations'] }),
  });
  const weight = (key: keyof BlindCreateRequest['weights_pct'], label: string) => (
    <label className="grid gap-1">
      {label}
      <Input
        type="number"
        min={0}
        max={100}
        value={String(form.weights_pct[key])}
        onChange={(event) =>
          setForm((current) => ({
            ...current,
            weights_pct: { ...current.weights_pct, [key]: Number(event.target.value) },
          }))
        }
      />
    </label>
  );
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }
  return (
    <details className="rounded-xl border bg-card p-5 text-sm">
      <summary className="cursor-pointer font-medium">Crear nueva validación ciega</summary>
      <p className="mt-2 text-muted-foreground">
        Por defecto, los parámetros de HIPOTESIS_CONGELADA.md: 20 posiciones equiponderadas, pesos
        30/35/25/10 y rebalanceo trimestral. Una validación nueva no tiene preregistro: su resultado
        se muestra al llegar la fecha de desbloqueo.
      </p>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-4"
        aria-label="Crear validación ciega"
        onSubmit={submit}
      >
        <label className="grid gap-1 sm:col-span-4">
          Nombre
          <Input
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </label>
        {weight('value', 'Peso Value (%)')}
        {weight('quality', 'Peso Quality (%)')}
        {weight('momentum', 'Peso Momentum (%)')}
        {weight('risk', 'Peso Risk (%)')}
        <label className="grid gap-1">
          Nº de posiciones
          <Input
            type="number"
            min={1}
            max={50}
            value={String(form.n_positions)}
            onChange={(event) => setForm({ ...form, n_positions: Number(event.target.value) })}
          />
        </label>
        <label className="grid gap-1">
          Rebalanceo
          <NativeSelect
            value={String(form.rebalance_months)}
            onChange={(event) =>
              setForm({
                ...form,
                rebalance_months: Number(
                  event.target.value,
                ) as BlindCreateRequest['rebalance_months'],
              })
            }
          >
            {[1, 3, 6, 12].map((months) => (
              <NativeSelectOption key={months} value={String(months)}>
                Cada {months} meses
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <label className="grid gap-1">
          Fecha de inicio
          <Input
            type="date"
            value={form.start_date}
            onChange={(event) => setForm({ ...form, start_date: event.target.value })}
          />
        </label>
        <label className="grid gap-1" title="Hasta esta fecha no se mostrará ningún rendimiento.">
          Fecha de desbloqueo
          <Input
            type="date"
            value={form.unlock_date}
            onChange={(event) => setForm({ ...form, unlock_date: event.target.value })}
          />
        </label>
        <Button type="submit" className="w-fit" disabled={create.isPending}>
          Crear validación
        </Button>
      </form>
      {create.isError && <ErrorState error={create.error} retry={() => create.reset()} />}
      {create.data && (
        <p className="mt-3" role="status">
          Validación #{create.data.id} creada — bloqueada hasta {create.data.unlock_date}.
        </p>
      )}
    </details>
  );
}

function BreakSeal({ item }: { item: BlindStatus }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('');
  const breakSeal = useMutation({
    mutationFn: () => breakBlindSeal(item.id, reason),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['research', 'blind-validations'] }),
  });
  return (
    <details className="mt-4 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        Romper el sello antes de tiempo (no recomendado)
      </summary>
      <p className="mt-2 text-xs text-muted-foreground">
        Esta app no puede impedirte mirar tus propios datos, pero si lo haces queda constancia
        permanente de que la prueba se rompió antes de tiempo y por qué.
      </p>
      <form
        className="mt-2 grid gap-2"
        aria-label={`Romper el sello de la validación ${item.id}`}
        onSubmit={(event) => {
          event.preventDefault();
          if (window.confirm('¿Romper el sello? Quedará registrado de forma permanente.'))
            breakSeal.mutate();
        }}
      >
        <label className="grid gap-1">
          Motivo (obligatorio)
          <textarea
            className="min-h-16 rounded-md border bg-transparent p-2"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <Button
          type="submit"
          variant="outline"
          className="w-fit"
          disabled={!reason.trim() || breakSeal.isPending}
        >
          Romper el sello
        </Button>
      </form>
      {breakSeal.isError && <ErrorState error={breakSeal.error} retry={() => breakSeal.reset()} />}
    </details>
  );
}

function Validation({ item }: { item: BlindStatus }) {
  const plan = item.preregistered;
  return (
    <article className="rounded-xl border bg-card p-5" aria-label={`Validación ${item.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">
          #{item.id} · {item.name}
        </h2>
        <span className="text-sm text-muted-foreground">
          {item.status === 'broken_early'
            ? 'Sello roto antes de tiempo'
            : item.revealed
              ? 'Desbloqueada'
              : 'Bloqueada'}
        </span>
      </div>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Periodos</dt>
          <dd>{item.n_periods}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Próximo rebalanceo</dt>
          <dd>
            {item.next_rebalance_due}
            {item.rebalance_due ? ' · toca registrar' : ''}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Desbloqueo</dt>
          <dd>
            {item.unlock_date}
            {!item.revealed && item.days_to_unlock > 0
              ? ` · faltan ${item.days_to_unlock} días`
              : ''}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Cadena de sellos</dt>
          <dd>{item.integrity.ok ? 'Íntegra' : `Alterada desde ${item.integrity.broken_at}`}</dd>
        </div>
      </dl>
      {plan && (
        <div className="mt-4 rounded-lg border p-3 text-sm" role="note">
          <p className="font-medium">Preregistro del #{plan.issue}</p>
          <p className="mt-1 text-muted-foreground">
            Revisiones fijadas: {plan.looks.join(', ')}. Solo se miran resultados en esas fechas: el
            rendimiento se calcula hasta la última revisión alcanzada y el sello no se puede romper
            antes.
            {item.next_look ? ` Próxima revisión: ${item.next_look}.` : ''}
            {item.revealed_through ? ` Visible hasta ${item.revealed_through}.` : ''}
          </p>
          <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
            {plan.source} · {plan.sha256}
          </p>
        </div>
      )}
      {!item.revealed && (
        <p className="mt-4 text-sm text-muted-foreground">
          Bloqueada: no se muestra ningún dato de rendimiento, ni siquiera si va ganando o perdiendo
          frente al SPY. Solo se confirma que los datos se registran correctamente.
        </p>
      )}
      <BlindActions item={item} />
      {!item.revealed && !plan && <BreakSeal item={item} />}
    </article>
  );
}

export function BlindValidationsPage() {
  const validations = useQuery({
    queryKey: ['research', 'blind-validations'],
    queryFn: ({ signal }) => getBlindValidations(signal),
  });
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/investigacion', label: 'Investigación' }}
        title="Validaciones ciegas"
        description={
          <>
            Cada rebalanceo queda registrado de forma inmutable (posiciones, precios y hash
            encadenado) y el rendimiento frente al SPY queda oculto hasta la fecha de desbloqueo.
            Esta vista no muestra posiciones ni precios. El backend aplica la fecha de desbloqueo y
            las revisiones de cada preregistro; ocultar un botón no basta.
          </>
        }
      >
        <p className="mt-3 max-w-3xl rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
          Ver el resultado a medias es la forma más humana de arruinar una prueba prospectiva: en
          cuanto se ajusta la estrategia por lo visto, la prueba deja de servir, aunque nadie haga
          trampa a propósito.
        </p>
      </PageHeader>
      <CreateValidation />
      {validations.isPending && <LoadingState />}
      {validations.isError && (
        <ErrorState error={validations.error} retry={() => void validations.refetch()} />
      )}
      {validations.data?.items.length === 0 && (
        <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
          No hay validaciones ciegas registradas en esta instalación.
        </p>
      )}
      {validations.data && validations.data.items.length > 0 && (
        <section className="grid gap-4" aria-label="Estado de validaciones ciegas">
          {validations.data.items.map((item) => (
            <Validation key={item.id} item={item} />
          ))}
        </section>
      )}
    </div>
  );
}
