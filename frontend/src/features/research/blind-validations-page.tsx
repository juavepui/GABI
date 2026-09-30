import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getBlindValidations } from '@/shared/api/client';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

export function BlindValidationsPage() {
  const validations = useQuery({
    queryKey: ['research', 'blind-validations'],
    queryFn: ({ signal }) => getBlindValidations(signal),
  });
  return (
    <div className="space-y-6">
      <header>
        <Link className="text-sm text-primary" to="/investigacion">
          ← Investigación
        </Link>
        <h1 className="mt-3 text-3xl font-semibold">Validaciones ciegas</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Estado e integridad de los sellos registrados. Esta vista no muestra posiciones, precios
          ni rendimiento. El alta y los rebalanceos siguen en Streamlit durante la migración.
        </p>
      </header>
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
            <article key={item.id} className="rounded-xl border bg-card p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-lg font-semibold">
                  #{item.id} · {item.name}
                </h2>
                <span className="text-sm text-muted-foreground">{item.status}</span>
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <dt className="text-muted-foreground">Periodos</dt>
                  <dd>{item.n_periods}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Próximo rebalanceo</dt>
                  <dd>{item.next_rebalance_due}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Desbloqueo</dt>
                  <dd>{item.unlock_date}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Cadena de sellos</dt>
                  <dd>
                    {item.integrity.ok ? 'Íntegra' : `Alterada desde ${item.integrity.broken_at}`}
                  </dd>
                </div>
              </dl>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
