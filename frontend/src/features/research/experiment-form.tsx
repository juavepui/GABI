import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createExperiment, deleteExperiment } from '@/shared/api/client';
import type { ExperimentStage, ManualExperimentRequest } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { NativeSelect, NativeSelectOption } from '@/shared/ui/native-select';
import { ErrorState } from '@/shared/ui/resource-state';

const today = () => new Date().toISOString().slice(0, 10);

function initial(): ManualExperimentRequest {
  return {
    model_id: 'GABI-MF-v1.0',
    n_positions: 20,
    rebalance: 'Quarterly',
    universe: 'S&P 500 histórico, muestra de 200',
    cost_model: '10pb por lado',
    family: '',
    data_cutoff: today(),
    is_start: '2016-07-02',
    is_end: '2025-04-01',
    sharpe: 0,
    sortino: 0,
    max_drawdown: 0,
    n_periods: 36,
    periods_per_year: 4,
    stage: 'RESEARCH',
    hypothesis_registered: false,
    data_fingerprint: '',
    notes: '',
  };
}

export function ManualExperimentForm({ stages }: { stages: ExperimentStage[] }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ManualExperimentRequest>(initial);
  const create = useMutation({
    mutationFn: () => createExperiment(form),
    onSuccess: () => {
      setForm(initial());
      void queryClient.invalidateQueries({ queryKey: ['research'] });
    },
  });
  const set = <K extends keyof ManualExperimentRequest>(
    key: K,
    value: ManualExperimentRequest[K],
  ) => setForm((current) => ({ ...current, [key]: value }));
  const text = (key: keyof ManualExperimentRequest, label: string) => (
    <label className="grid gap-1">
      {label}
      <Input
        value={String(form[key] ?? '')}
        onChange={(event) => set(key, event.target.value as never)}
      />
    </label>
  );
  const number = (
    key: keyof ManualExperimentRequest,
    label: string,
    options: { step?: string; min?: number; max?: number; title?: string } = {},
  ) => (
    <label className="grid gap-1" title={options.title}>
      {label}
      <Input
        type="number"
        step={options.step ?? 'any'}
        min={options.min}
        max={options.max}
        value={String(form[key])}
        onChange={(event) => set(key, Number(event.target.value) as never)}
      />
    </label>
  );
  const day = (key: 'data_cutoff' | 'is_start' | 'is_end', label: string) => (
    <label className="grid gap-1">
      {label}
      <Input type="date" value={form[key]} onChange={(event) => set(key, event.target.value)} />
    </label>
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <details className="rounded-xl border bg-card p-5 text-sm">
      <summary className="cursor-pointer font-medium">Registrar experimento manualmente</summary>
      <p className="mt-2 text-muted-foreground">
        Para experimentos que no vienen de un backtest de Investigación → Ranking histórico (por
        ejemplo, resultados calculados fuera de la aplicación).
      </p>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-3"
        onSubmit={submit}
        aria-label="Registrar experimento"
      >
        {text('model_id', 'Model ID')}
        {number('n_positions', 'Nº posiciones', { step: '1', min: 1, max: 100 })}
        <label className="grid gap-1">
          Rebalanceo
          <NativeSelect
            value={form.rebalance}
            onChange={(event) =>
              set('rebalance', event.target.value as ManualExperimentRequest['rebalance'])
            }
          >
            {(['Quarterly', 'Semiannual', 'Annual', 'Monthly'] as const).map((value) => (
              <NativeSelectOption key={value} value={value}>
                {value}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        {text('universe', 'Universo')}
        {text('cost_model', 'Modelo de costes')}
        {text('family', 'Familia (agrupa intentos comparables)')}
        {day('data_cutoff', 'Corte de datos')}
        {day('is_start', 'Inicio periodo IS')}
        {day('is_end', 'Fin periodo IS')}
        {number('sharpe', 'Sharpe')}
        {number('sortino', 'Sortino')}
        {number('max_drawdown', 'Máx. drawdown', {
          title: 'Como fracción negativa, por ejemplo -0,25 = -25 %.',
        })}
        {number('n_periods', 'Nº de periodos', { step: '1', min: 1 })}
        {number('periods_per_year', 'Periodos por año', { min: 1 })}
        <label className="grid gap-1">
          Fase
          <NativeSelect
            value={form.stage}
            onChange={(event) =>
              set('stage', event.target.value as ManualExperimentRequest['stage'])
            }
          >
            {stages.map((stage) => (
              <NativeSelectOption key={stage.id} value={stage.id}>
                {stage.emoji} {stage.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </label>
        <label className="flex items-center gap-2 sm:col-span-3">
          <input
            type="checkbox"
            checked={form.hypothesis_registered}
            onChange={(event) => set('hypothesis_registered', event.target.checked)}
          />
          ¿Hipótesis registrada formalmente antes de ver el resultado?
        </label>
        <label
          className="grid gap-1 sm:col-span-3"
          title="Pega la huella capturada al ejecutar el experimento. Si no existe, queda sin trazabilidad de datos."
        >
          Fingerprint de datos del run
          <Input
            value={form.data_fingerprint ?? ''}
            onChange={(event) => set('data_fingerprint', event.target.value)}
          />
        </label>
        <label className="grid gap-1 sm:col-span-3">
          Notas
          <textarea
            className="min-h-20 rounded-md border bg-transparent p-2"
            value={form.notes ?? ''}
            onChange={(event) => set('notes', event.target.value)}
          />
        </label>
        <p className="text-xs text-muted-foreground sm:col-span-3">
          Un 0 en Sharpe, Sortino o drawdown se guarda como «sin dato», igual que antes. Se
          registran también el commit, las versiones de dependencias y la huella de uv.lock.
        </p>
        <Button type="submit" className="w-fit" disabled={create.isPending}>
          Registrar
        </Button>
      </form>
      {create.isError && <ErrorState error={create.error} retry={() => create.reset()} />}
      {create.data && (
        <p className="mt-3 text-sm" role="status">
          Experimento #{create.data.id} registrado.
        </p>
      )}
    </details>
  );
}

export function DeleteExperiment() {
  const queryClient = useQueryClient();
  const [id, setId] = useState(0);
  const remove = useMutation({
    mutationFn: () => deleteExperiment(id),
    onSuccess: () => {
      setId(0);
      void queryClient.invalidateQueries({ queryKey: ['research'] });
    },
  });
  return (
    <form
      className="flex flex-wrap items-end gap-3 text-sm"
      aria-label="Eliminar experimento"
      onSubmit={(event) => {
        event.preventDefault();
        if (id > 0 && window.confirm(`¿Eliminar el experimento #${id}? No se puede deshacer.`))
          remove.mutate();
      }}
    >
      <label className="grid gap-1">
        Eliminar experimento por id
        <Input
          type="number"
          min={0}
          step="1"
          value={String(id)}
          onChange={(event) => setId(Math.max(0, Math.trunc(Number(event.target.value))))}
        />
      </label>
      <Button type="submit" variant="outline" disabled={id === 0 || remove.isPending}>
        Eliminar
      </Button>
      {remove.isError && <ErrorState error={remove.error} retry={() => remove.reset()} />}
      {remove.data && <p role="status">Experimento #{remove.data.deleted} eliminado.</p>}
    </form>
  );
}
