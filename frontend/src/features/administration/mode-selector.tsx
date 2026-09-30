import { useMutation, useQueryClient } from '@tanstack/react-query';
import { setMode } from '@/shared/api/client';
import type { ModelResponse } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';

export function ModeSelector({ model }: { model: ModelResponse }) {
  const client = useQueryClient();
  const change = useMutation({
    mutationFn: setMode,
    onSuccess: () => void client.invalidateQueries(),
  });
  const research = model.mode === 'RESEARCH';
  return (
    <div className="mt-5 space-y-2 border-t pt-5">
      <p className="text-sm font-medium">Modo de trabajo · {research ? 'Research' : 'Investor'}</p>
      <p className="text-xs text-muted-foreground">
        {research
          ? 'Research permite experimentar; sus resultados no se convierten en evidencia validada.'
          : 'Investor utiliza los pesos congelados y bloquea los trabajos de investigación.'}
      </p>
      <Button
        type="button"
        variant="outline"
        disabled={change.isPending}
        onClick={() => change.mutate(research ? 'INVESTOR' : 'RESEARCH')}
      >
        {research ? 'Activar Investor' : 'Activar Research'}
      </Button>
      {change.isError && (
        <p role="alert" className="text-xs text-destructive">
          {change.error.message}
        </p>
      )}
    </div>
  );
}
