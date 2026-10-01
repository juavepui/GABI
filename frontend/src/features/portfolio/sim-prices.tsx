import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getJobResult } from '@/shared/api/client';
import { useJob } from '@/shared/api/use-job';
import { Button } from '@/shared/ui/button';
import { Input } from '@/shared/ui/input';
import { ErrorState } from '@/shared/ui/resource-state';
import { ProgressBar } from '@/shared/ui/progress-bar';

type PricesResult = {
  symbols: string[];
  updated: number;
  failed: Record<string, string>;
};

/** The old price buttons: one ticker with SPY and FX pairs, or every traded symbol with SPY. */
export function SimulationPrices({
  portfolioId,
  hasTrades,
}: {
  portfolioId: number;
  hasTrades: boolean;
}) {
  const queryClient = useQueryClient();
  const [symbol, setSymbol] = useState('');
  const { start, job } = useJob('sim-prices');
  const running = start.isPending || ['queued', 'running'].includes(job.data?.status ?? '');
  const result = useQuery({
    queryKey: ['job', job.data?.id, 'result'],
    queryFn: ({ signal }) => getJobResult(job.data!.id, signal) as Promise<PricesResult>,
    enabled: job.data?.status === 'succeeded',
  });
  const done = result.data != null;
  useEffect(() => {
    if (done)
      void queryClient.invalidateQueries({ queryKey: ['portfolio', 'simulations', portfolioId] });
  }, [done, portfolioId, queryClient]);
  const run = (symbols: string[]) =>
    start.mutate({ kind: 'sim_prices', portfolio_id: portfolioId, symbols });
  const failed = Object.entries(result.data?.failed ?? {});
  return (
    <section className="rounded-xl border bg-card p-5" aria-label="Precios públicos">
      <h2 className="text-lg font-semibold">Precios públicos</h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Descarga el histórico completo de Yahoo Finance de un ticker (con el SPY y los tipos de
        cambio de la cartera) o de todos los valores operados en ella y el SPY. Es una descarga
        explícita: el worker la ejecuta aunque cierres el navegador.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs font-medium">
          Ticker
          <Input
            value={symbol}
            placeholder="AAPL"
            onChange={(event) => setSymbol(event.target.value.toUpperCase().trim())}
          />
        </label>
        <Button variant="outline" disabled={running || !symbol} onClick={() => run([symbol])}>
          Actualizar precios de este ticker
        </Button>
        <Button variant="outline" disabled={running || !hasTrades} onClick={() => run([])}>
          Actualizar precios de esta cartera y SPY
        </Button>
      </div>
      {start.isError && <ErrorState error={start.error} retry={() => start.reset()} />}
      {job.data && job.data.status !== 'succeeded' && (
        <div className="mt-3">
          <ProgressBar value={job.data.progress} phase={job.data.phase} status={job.data.status} />
        </div>
      )}
      {job.data?.status === 'failed' && (
        <p className="mt-2 text-xs text-destructive">La descarga no terminó.</p>
      )}
      {result.data && (
        <div role="status" className="mt-2 space-y-1 text-sm">
          <p>
            Actualizados {result.data.updated} símbolos; fallos: {failed.length}.
          </p>
          {failed.length > 0 && (
            <ul className="text-xs text-destructive">
              {failed.map(([name, reason]) => (
                <li key={name}>
                  {name}: {reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
