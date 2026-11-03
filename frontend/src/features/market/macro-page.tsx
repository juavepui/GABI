import { Link } from 'react-router-dom';
import { dateLabel, formatNumber } from '@/shared/lib/format';
import { LoadingState, ErrorState } from '@/shared/ui/resource-state';
import { PageHeader } from '@/shared/ui/page-header';
import { amount, cadence, trend, useMacro } from './macro-format';

export function MacroPage() {
  const query = useMacro();
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/', label: 'Hoy' }}
        title="Economía (macro)"
        description={
          <>
            Cómo está la economía de EE. UU.: tipos de interés, inflación, dólar y señales de
            recesión. Es contexto para tus decisiones; no cambia la puntuación de las empresas.
          </>
        }
        guide={
          <>
            <p>
              Útil para tus notas del{' '}
              <Link className="text-primary underline" to="/cartera/diario">
                diario de inversión
              </Link>
              : por ejemplo, si los tipos de interés suben, las empresas cuyo beneficio está muy
              lejos en el futuro suelen sufrir más. Los datos son de FRED (la base de datos pública
              de la Reserva Federal) y se leen de tu equipo; abrir esta página no descarga nada.
            </p>
          </>
        }
      />
      {query.isPending && <LoadingState />}
      {query.isError && <ErrorState error={query.error} retry={() => void query.refetch()} />}
      {query.data && (
        <>
          {!query.data.fred_key_configured && (
            <p
              role="note"
              className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
            >
              Falta la clave de FRED, así que estos datos no se pueden actualizar: ves los que ya
              estaban guardados. Es gratuita; guárdala en{' '}
              <Link className="underline" to="/administracion">
                Administración
              </Link>{' '}
              para refrescarlas.
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {query.data.items.map((item) => (
              <article key={item.series_id} className="rounded-xl border bg-card p-5">
                <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
                <p className="mt-3 text-2xl font-semibold tabular-nums">
                  {item.unit === 'USD' ? (
                    amount(item.latest_value, item.unit)
                  ) : (
                    <>
                      {formatNumber(item.latest_value, { digits: 2 })}{' '}
                      <span className="text-sm font-normal">{item.unit}</span>
                    </>
                  )}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {item.latest_value == null
                    ? 'Sin datos guardados'
                    : 'Dato del ' + dateLabel(item.latest_date)}
                  {item.change_3m != null && (
                    <>
                      {' · Cambio en 3 meses: '}
                      <span aria-hidden="true">{trend(item.change_3m)} </span>
                      {amount(item.change_3m, item.change_unit, true)}
                    </>
                  )}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Fuente: FRED ({item.series_id}) · {cadence(item)}
                </p>
                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">{item.help}</p>
              </article>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">
            Para actualizar las series, usa «Actualización completa» en{' '}
            <Link className="text-primary underline" to="/administracion">
              Administración
            </Link>
            . La fecha del próximo dato de inflación (IPC) no se muestra porque habría que
            consultarla en internet.
          </p>
        </>
      )}
    </div>
  );
}
