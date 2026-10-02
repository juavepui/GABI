import { useMutation, useQueryClient } from '@tanstack/react-query';
import { setMode } from '@/shared/api/client';
import type { ModelResponse } from '@/shared/api/generated/types.gen';
import { Button } from '@/shared/ui/button';
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

export function ModeSelector({ model }: { model: ModelResponse }) {
  const client = useQueryClient();
  const change = useMutation({
    mutationFn: setMode,
    onSuccess: () => void client.invalidateQueries(),
  });
  const research = model.mode === 'RESEARCH';
  const { hash } = useLocation();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (hash !== '#modo') return;
    // Cards above it (keys, jobs) finish loading after this one mounts and push it down:
    // scroll now and again once the page has settled.
    const scroll = () => box.current?.scrollIntoView({ block: 'center' });
    scroll();
    const timer = window.setTimeout(scroll, 600);
    return () => window.clearTimeout(timer);
  }, [hash]);
  return (
    <div
      id="modo"
      ref={box}
      className={
        'mt-5 scroll-mt-24 space-y-2 border-t pt-5 ' +
        (hash === '#modo' ? 'rounded-lg bg-accent/60 p-3' : '')
      }
    >
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
