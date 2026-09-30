import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { getResearchOverview, getResearchTrials } from '@/shared/api/client';
import { Button } from '@/shared/ui/button';
import { ErrorState, LoadingState } from '@/shared/ui/resource-state';

const PAGE_SIZE = 25;

const decisionLabel: Record<string, string> = {
  retained_for_audit: 'Conservado para auditoría',
  historically_selected: 'Seleccionado históricamente',
  failed_daily_gate: 'No superó el criterio',
  await_preregistered_looks: 'Pendiente de cortes preregistrados',
  not_promoted: 'No promovido',
  secondary_not_promoted: 'Análisis secundario',
  reference: 'Referencia',
  descartar: 'Descartado',
};

export function ResearchPage() {
  const [params, setParams] = useSearchParams();
  const requestedPage = Number(params.get('page') ?? '1');
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const family = params.get('family') ?? '';
  const offset = (page - 1) * PAGE_SIZE;
  const overview = useQuery({
    queryKey: ['research', 'overview'],
    queryFn: ({ signal }) => getResearchOverview(signal),
  });
  const trials = useQuery({
    queryKey: ['research', 'trials', offset, family],
    queryFn: ({ signal }) => getResearchTrials(offset, family, signal),
  });

  function changeFilter(nextFamily: string, nextPage = 1) {
    const next = new URLSearchParams();
    if (nextFamily) next.set('family', nextFamily);
    if (nextPage > 1) next.set('page', String(nextPage));
    setParams(next);
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Evidencia publicada
        </p>
        <h1 className="mt-3 text-3xl font-semibold">Investigación</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          Registro de búsquedas y resultados publicados. Los ensayos retrospectivos no son una
          validación independiente. GABI todavía no ha demostrado una estrategia neta claramente
          superior al S&amp;P 500.
        </p>
        <Link
          className="mt-3 inline-block text-sm font-medium text-primary underline"
          to="/investigacion/historico"
        >
          Abrir ranking histórico →
        </Link>
      </header>

      {(overview.isPending || trials.isPending) && <LoadingState />}
      {overview.isError && (
        <ErrorState error={overview.error} retry={() => void overview.refetch()} />
      )}
      {trials.isError && <ErrorState error={trials.error} retry={() => void trials.refetch()} />}

      {overview.data && (
        <section className="grid gap-4 sm:grid-cols-3" aria-label="Estado del registro">
          <div className="rounded-xl border bg-card p-5">
            <p className="text-xs text-muted-foreground">Convención histórica</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {overview.data.counts.legacy_guard_entries ?? '—'}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">No es un recuento exhaustivo</p>
          </div>
          <div className="rounded-xl border bg-card p-5">
            <p className="text-xs text-muted-foreground">Confirmación independiente</p>
            <p className="mt-2 text-lg font-semibold">No acreditada</p>
            <p className="mt-1 text-xs text-muted-foreground">
              La ventaja frente al índice sigue pendiente
            </p>
          </div>
          <div className="rounded-xl border bg-card p-5">
            <p className="text-xs text-muted-foreground">Estado del catálogo</p>
            <p className="mt-2 text-lg font-semibold">Publicado · {overview.data.as_of}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {overview.data.diagnostics.length} grupos diagnósticos separados
            </p>
          </div>
        </section>
      )}

      {overview.data && trials.data && (
        <section className="rounded-xl border bg-card p-5">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">Ensayos registrados</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {trials.data.total} registros para este filtro; se muestran también los fallidos.
              </p>
            </div>
            <label className="text-xs font-medium">
              Familia
              <select
                className="mt-1.5 block h-10 min-w-48 rounded-md border bg-background px-2 text-sm"
                value={family}
                onChange={(event) => changeFilter(event.target.value)}
              >
                <option value="">Todas</option>
                {overview.data.families.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="py-2 pr-3">Ensayo</th>
                  <th className="py-2 pr-3">Muestra</th>
                  <th className="py-2 pr-3">Decisión</th>
                  <th className="py-2">Procedencia</th>
                </tr>
              </thead>
              <tbody>
                {trials.data.items.map((item) => (
                  <tr key={item.id} className="border-b align-top last:border-0">
                    <td className="py-3 pr-3">
                      <span className="font-medium">{item.id}</span>
                      <span className="block text-xs text-muted-foreground">{item.family}</span>
                    </td>
                    <td className="py-3 pr-3">
                      {item.state === 'observed'
                        ? 'Retrospectiva observada'
                        : 'Prospectiva pendiente'}
                    </td>
                    <td className="py-3 pr-3">
                      {decisionLabel[item.decision] ?? item.decision}
                      {item.failures && item.failures.length > 0 && (
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {item.failures.join(', ')}
                        </span>
                      )}
                    </td>
                    <td className="py-3 text-xs">
                      <span className="block break-all">{item.specification_ref}</span>
                      <span className="block break-all text-muted-foreground">
                        {item.result_ref ?? 'Resultado aún no disponible'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-5 flex items-center gap-3">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => changeFilter(family, page - 1)}
            >
              Anterior
            </Button>
            <span className="text-xs text-muted-foreground">Página {page}</span>
            <Button
              variant="outline"
              disabled={offset + PAGE_SIZE >= trials.data.total}
              onClick={() => changeFilter(family, page + 1)}
            >
              Siguiente
            </Button>
          </div>
        </section>
      )}

      {overview.data && (
        <section className="rounded-xl border bg-card p-5">
          <h2 className="text-lg font-semibold">Límites de la evidencia</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            {overview.data.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-muted-foreground">
            Las reservas ciegas y los resultados aún no publicados no se consultan desde este
            catálogo. Ranking histórico, laboratorios y validación ciega siguen disponibles en
            Streamlit mientras se verifican sus sustitutos.
          </p>
        </section>
      )}
    </div>
  );
}

export { HistoricalPage } from './historical-page';
