import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveWeights } from '@/shared/api/client';
import type { ModelResponse, WeightsRequest } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { formatNumber } from '@/shared/lib/format';
import { Input } from '@/shared/ui/input';

const fields = [
  ['value', 'Valor'],
  ['quality', 'Calidad'],
  ['momentum', 'Momento'],
  ['risk', 'Riesgo'],
] as const;

export function WeightsEditor({ model }: { model: ModelResponse }) {
  const client = useQueryClient();
  // Percent with two decimals for the inputs (a value to edit, not a text to show).
  const percent = (fraction: number | undefined) => Math.round((fraction ?? 0) * 10000) / 100;
  const [draft, setDraft] = useState<WeightsRequest>(() => ({
    value: percent(model.weights.value),
    quality: percent(model.weights.quality),
    momentum: percent(model.weights.momentum),
    risk: percent(model.weights.risk),
  }));
  const save = useMutation({
    mutationFn: saveWeights,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['model'] });
      void client.invalidateQueries({ queryKey: ['market'] });
    },
  });
  const total = Object.values(draft).reduce((sum, value) => sum + value, 0);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (Math.abs(total - 100) > 0.001) return;
        save.mutate({
          value: draft.value / 100,
          quality: draft.quality / 100,
          momentum: draft.momentum / 100,
          risk: draft.risk / 100,
        });
      }}
      className="mt-5 space-y-3 border-t pt-5"
    >
      <p className="text-sm font-medium">
        Pesos del modelo · {model.mode === 'INVESTOR' ? 'Investor, bloqueados' : 'Research'}
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {fields.map(([key, label]) => (
          <label key={key} className="text-xs">
            {label} (%)
            <Input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={draft[key]}
              disabled={model.mode !== 'RESEARCH'}
              onChange={(event) =>
                setDraft((current) => ({ ...current, [key]: Number(event.target.value) }))
              }
              className="mt-1"
            />
          </label>
        ))}
      </div>
      {model.mode === 'RESEARCH' ? (
        <>
          <p className="text-xs text-muted-foreground">
            Total: {formatNumber(total, { digits: 2, fixed: true })} %. Solo se guardan si suman 100
            %.
          </p>
          <Button
            type="submit"
            variant="outline"
            disabled={save.isPending || Math.abs(total - 100) > 0.001}
          >
            Guardar pesos
          </Button>
          {save.isSuccess && (
            <p role="status" className="text-xs text-primary">
              Pesos guardados en este equipo.
            </p>
          )}
          {save.isError && (
            <p role="alert" className="text-xs text-destructive">
              {save.error.message}
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          El modo Investor utiliza los pesos congelados. Activa Research arriba para editar sus
          valores por defecto.
        </p>
      )}
    </form>
  );
}
