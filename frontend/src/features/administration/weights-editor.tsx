import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveWeights } from '@/shared/api/client';
import type { ModelResponse, WeightsRequest } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';

const fields = [
  ['value', 'Valor'],
  ['quality', 'Calidad'],
  ['momentum', 'Momento'],
  ['risk', 'Riesgo'],
] as const;

export function WeightsEditor({ model }: { model: ModelResponse }) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<WeightsRequest>(() => ({
    value: Number(((model.weights.value ?? 0) * 100).toFixed(2)),
    quality: Number(((model.weights.quality ?? 0) * 100).toFixed(2)),
    momentum: Number(((model.weights.momentum ?? 0) * 100).toFixed(2)),
    risk: Number(((model.weights.risk ?? 0) * 100).toFixed(2)),
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
            <input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={draft[key]}
              disabled={model.mode !== 'RESEARCH'}
              onChange={(event) =>
                setDraft((current) => ({ ...current, [key]: Number(event.target.value) }))
              }
              className="mt-1 w-full rounded-md border bg-background p-2 text-sm"
            />
          </label>
        ))}
      </div>
      {model.mode === 'RESEARCH' ? (
        <>
          <p className="text-xs text-muted-foreground">
            Total: {total.toFixed(2)} %. Solo se guardan si suman 100 %.
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
