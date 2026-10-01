import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getMacro } from '@/shared/api/client';
import { dateLabel } from '@/shared/lib/format';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { BackLink } from '@/shared/ui/section-links';

const value = (amount: number | null) =>
  amount == null
    ? '—'
    : new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(amount);

export function MacroPage() {
  const query = useQuery({
    queryKey: ['market', 'macro'],
    queryFn: ({ signal }) => getMacro(signal),
  });
  return (
    <div className="space-y-6">
      <header>
        <BackLink to="/mercado">Mercado</BackLink>
        <h1 className="mt-3 text-3xl font-semibold">Panel macro</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Contexto para las tesis del{' '}
          <Link className="text-primary underline" to="/cartera/diario">
            diario de inversión
          </Link>
          . Estas series FRED no intervienen en el score de empresas. La consulta solo lee datos
          descargados en este equipo.
        </p>
      </header>
      {query.isPending && <LoadingState />}
      {query.isError && <ErrorState error={query.error} retry={() => void query.refetch()} />}
      {query.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {query.data.items.map((item) => (
              <article key={item.series_id} className="rounded-xl border bg-card p-5">
                <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
                <p className="mt-3 text-2xl font-semibold tabular-nums">
                  {value(item.latest_value)}{' '}
                  <span className="text-sm font-normal">{item.unit}</span>
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {item.latest_value == null
                    ? 'Sin dato local'
                    : 'Dato a ' + dateLabel(item.latest_date)}
                  {item.change_3m != null &&
                    ' · Cambio frente a 3 meses: ' + value(item.change_3m) + ' ' + item.unit}
                </p>
                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">{item.help}</p>
              </article>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">
            Para actualizar las series, usa el job «Actualizar datos del mercado» en{' '}
            <Link className="text-primary underline" to="/administracion">
              Administración
            </Link>
            . La fecha de la próxima publicación CPI requiere una consulta externa y no se obtiene
            al abrir este panel.
          </p>
        </>
      )}
    </div>
  );
}
