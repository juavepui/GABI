import { useQuery } from '@tanstack/react-query';
import { getEstimateCaptures } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

export function EstimateCaptures() {
  const query = useQuery({
    queryKey: ['research', 'estimate-captures'],
    queryFn: ({ signal }) => getEstimateCaptures(signal),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data;
  if (!data) return null;
  return (
    <section className="rounded-xl border bg-card p-5" aria-labelledby="estimate-captures-heading">
      <h2 id="estimate-captures-heading" className="text-xl font-semibold">
        Estimaciones de consenso
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Archivo experimental de capturas reales del consenso. Yahoo no ofrece el historial de
        estimaciones de fechas pasadas; GABI solo puede estudiar las fotos guardadas desde cada
        sincronización. Esta consulta no calcula retornos ni Rank IC.
      </p>
      <p className="mt-3 text-sm">
        {data.batches_eligible} de {data.batches_total} capturas tienen al menos{' '}
        {data.symbols_per_batch_needed} empresas. Se necesitan {data.batches_needed} capturas
        separadas por {data.span_days_needed} días; el margen actual es de {data.span_days} días.
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        {data.history_threshold_met
          ? 'Hay profundidad suficiente para plantear un experimento explícito, sujeto al corte observado y al registro previo.'
          : 'Aún falta profundidad para plantear el experimento.'}{' '}
        Ninguna ventaja frente al S&amp;P 500 queda demostrada por estas capturas.
      </p>
    </section>
  );
}
